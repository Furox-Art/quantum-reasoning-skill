<?php

/**
 * This file is part of PHPWord - A pure PHP library for reading and writing
 * word processing documents.
 *
 * PHPWord is free software distributed under the terms of the GNU Lesser
 * General Public License version 3 as published by the Free Software Foundation.
 *
 * For the full copyright and license information, please read the LICENSE
 * file that was distributed with this source code. For the full list of
 * contributors, visit https://github.com/PHPOffice/PHPWord/contributors.
 *
 * @see         https://github.com/PHPOffice/PHPWord
 *
 * @license     http://www.gnu.org/licenses/lgpl.txt LGPL version 3
 */

namespace PhpOffice\PhpWord\Writer\WPS;

use InvalidArgumentException;
use RuntimeException;

/**
 * Encoder for the Microsoft Works 7/8 CONTENTS stream.
 *
 * Supported inline objects use:
 *   TEXT U+FFFC + FDPC(Object) + EOBJ metadata.
 * Images additionally use CFB Object N/Ole10Native streams.
 * Tables additionally use STRS(type 5) + TCD + FRAM + MCLD.
 */
final class Contents
{
    public function encode(string $text, array $images = [], array $tables = [], array $styles = []): string
    {
        $text = $this->normalizeText($text);
        $mainTextBytes = Utf16::encodeLe($text);
        $mainUnits = intdiv(strlen($mainTextBytes), 2);

        $fontRuns = isset($styles['fontRuns']) && is_array($styles['fontRuns']) ? $styles['fontRuns'] : [];
        $paragraphRuns = isset($styles['paragraphRuns']) && is_array($styles['paragraphRuns']) ? $styles['paragraphRuns'] : [];
        $tableUnitBase = $mainUnits;
        foreach ($tables as $table) {
            foreach (($table['fontRuns'] ?? []) as $run) {
                $run['startUnit'] += $tableUnitBase;
                $run['endUnit'] += $tableUnitBase;
                $fontRuns[] = $run;
            }
            foreach (($table['paragraphRuns'] ?? []) as $run) {
                $run['startUnit'] += $tableUnitBase;
                $run['endUnit'] += $tableUnitBase;
                $paragraphRuns[] = $run;
            }
            $tableUnitBase += (int) $table['zoneUnits'];
        }
        $fontRuns = $this->normalizeRuns($fontRuns, 'font');
        $paragraphRuns = $this->normalizeRuns($paragraphRuns, 'paragraph');

        $fontNames = [];
        foreach ($fontRuns as $run) {
            $name = (string) $run['font']['name'];
            if (!in_array($name, $fontNames, true)) {
                $fontNames[] = $name;
            }
        }
        $font = $this->encodeFontTable($fontNames);
        $fontIds = array_flip($fontNames);

        $objects = [];
        foreach ($images as $image) {
            $image['objectType'] = 2;
            $objects[] = $image;
        }
        foreach ($tables as $table) {
            $table['objectType'] = 3;
            $objects[] = $table;
        }
        usort($objects, static function ($a, $b): int {
            return ((int) $a['textUnitOffset']) <=> ((int) $b['textUnitOffset']);
        });

        $hasFdpc = $objects !== [] || $fontRuns !== [];
        $hasFdpp = $paragraphRuns !== [];
        $zoneCount = 2;
        if ($hasFdpc) {
            ++$zoneCount;
        }
        if ($objects !== []) {
            ++$zoneCount; // EOBJ
        }
        if ($hasFdpp) {
            ++$zoneCount;
        }
        if ($tables !== []) {
            $zoneCount += 3 + count($tables); // STRS + FRAM + MCLD + TCD per table
        }

        $headerSize = $this->indexRegionSize($zoneCount);
        $fontOffset = $headerSize;
        $textOffset = $fontOffset + strlen($font);

        $fullTextBytes = $mainTextBytes;
        foreach ($tables as $table) {
            $fullTextBytes .= Utf16::encodeLe($this->normalizeText($table['zoneText']));
        }
        $mainTextEnd = $textOffset + strlen($mainTextBytes);
        $fullTextEnd = $textOffset + strlen($fullTextBytes);

        $zones = [
            ['FONT', 'FONT', 0, $font],
            ['TEXT', 'TEXT', 0, $fullTextBytes],
        ];

        if ($tables !== []) {
            $zones[] = ['STRS', 'PLC ', 0, $this->encodeStrs($mainUnits, $tables)];
            foreach ($tables as $table) {
                $zones[] = ['TCD ', 'PLC ', (int) $table['strsId'], $this->encodeTcd($table['cellEndUnitOffsets'])];
            }
        }

        if ($hasFdpc) {
            $zones[] = ['FDPC', 'FDPC', 0, $this->encodeFdpc($objects, $fontRuns, $fontIds, $textOffset, $mainTextEnd, $fullTextEnd)];
        }
        if ($objects !== []) {
            // id 0 is the main STRS vector index; when STRS is absent libwps
            // falls back to the single main TEXT zone with the same effective id.
            $zones[] = ['EOBJ', 'PLC ', 0, $this->encodeEobj($objects)];
        }
        if ($hasFdpp) {
            $zones[] = ['FDPP', 'FDPP', 0, $this->encodeFdpp($paragraphRuns, $textOffset, $fullTextEnd)];
        }

        if ($tables !== []) {
            $zones[] = ['FRAM', 'FRAM', 0, $this->encodeFram($tables)];
            $zones[] = ['MCLD', 'MCLD', 0, $this->encodeMcld($tables)];
        }

        if (count($zones) !== $zoneCount) {
            throw new RuntimeException('Internal WPS zone-count mismatch.');
        }

        $offset = $headerSize;
        $indexed = [];
        foreach ($zones as $zone) {
            $indexed[] = [
                'name' => $zone[0],
                'type' => $zone[1],
                'id' => $zone[2],
                'offset' => $offset,
                'length' => strlen($zone[3]),
            ];
            $offset += strlen($zone[3]);
        }

        $data = $this->encodeIndexRegion($indexed);
        if (strlen($data) !== $headerSize) {
            throw new RuntimeException('Internal WPS header size mismatch.');
        }
        foreach ($zones as $zone) {
            $data .= $zone[3];
        }

        // The CFB writer deliberately keeps CONTENTS outside the Mini Stream.
        if (strlen($data) < 4096) {
            $data .= str_repeat("\0", 4096 - strlen($data));
        }

        return $data;
    }

    private function encodeFdpc(array $objects, array $fontRuns, array $fontIds, int $textOffset, int $mainTextEnd, int $fullTextEnd): string
    {
        $events = [];

        // Resets are registered first. A style starting at the same boundary
        // must win over the reset from the previous run.
        foreach ($fontRuns as $run) {
            $end = $textOffset + 2 * (int) $run['endUnit'];
            if ($end < $fullTextEnd) {
                $events[$end] = null;
            }
        }
        foreach ($objects as $object) {
            $start = $textOffset + 2 * (int) $object['textUnitOffset'];
            $end = $start + 2;
            if ($start < $textOffset || $end > $mainTextEnd) {
                throw new RuntimeException('Inline object position is outside the main TEXT zone.');
            }
            if ($end < $fullTextEnd) {
                $events[$end] = null;
            }
        }

        foreach ($fontRuns as $run) {
            $start = $textOffset + 2 * (int) $run['startUnit'];
            $end = $textOffset + 2 * (int) $run['endUnit'];
            if ($start < $textOffset || $end <= $start || $end > $fullTextEnd) {
                throw new RuntimeException('Character style range is outside the Works TEXT zone.');
            }
            $events[$start] = ['kind' => 'font', 'font' => $run['font']];
        }
        foreach ($objects as $object) {
            $start = $textOffset + 2 * (int) $object['textUnitOffset'];
            $events[$start] = ['kind' => 'object']; // object wins at U+FFFC
        }
        ksort($events, SORT_NUMERIC);

        $count = count($events);
        if ($count < 1 || $count > 65535) {
            throw new RuntimeException('Invalid FDPC event count.');
        }

        $headerSize = 8 + 6 * $count;
        $properties = '';
        $propertyOffsets = [];
        $cache = [];
        foreach ($events as $event) {
            if ($event === null) {
                $propertyOffsets[] = 0;

                continue;
            }
            if ($event['kind'] === 'object') {
                $key = 'object';
                $property = $this->objectFontProperty();
            } else {
                $font = $event['font'];
                $name = (string) $font['name'];
                if (!array_key_exists($name, $fontIds)) {
                    throw new RuntimeException('Character property references a font missing from FONT.');
                }
                $key = 'font:' . serialize($font);
                $property = $this->fontProperty($font, (int) $fontIds[$name]);
            }
            if (!isset($cache[$key])) {
                $relative = $headerSize + strlen($properties);
                if ($relative > 0xFFFF) {
                    throw new RuntimeException('FDPC property offsets exceed the 16-bit Works limit.');
                }
                $cache[$key] = $relative;
                $properties .= $property;
            }
            $propertyOffsets[] = $cache[$key];
        }

        $data = $this->u16($count) . $this->u16(0);
        foreach (array_keys($events) as $position) {
            $data .= $this->u32($position);
        }
        $data .= $this->u32($fullTextEnd);
        foreach ($propertyOffsets as $propertyOffset) {
            $data .= $this->u16($propertyOffset);
        }
        $data .= $properties;

        return $data;
    }

    private function encodeFdpp(array $paragraphRuns, int $textOffset, int $fullTextEnd): string
    {
        $events = [];
        foreach ($paragraphRuns as $run) {
            $end = $textOffset + 2 * (int) $run['endUnit'];
            if ($end < $fullTextEnd) {
                $events[$end] = null;
            }
        }
        foreach ($paragraphRuns as $run) {
            $start = $textOffset + 2 * (int) $run['startUnit'];
            $end = $textOffset + 2 * (int) $run['endUnit'];
            if ($start < $textOffset || $end <= $start || $end > $fullTextEnd) {
                throw new RuntimeException('Paragraph style range is outside the Works TEXT zone.');
            }
            $events[$start] = ['paragraph' => $run['paragraph']];
        }
        ksort($events, SORT_NUMERIC);
        $count = count($events);
        if ($count < 1 || $count > 65535) {
            throw new RuntimeException('Invalid FDPP event count.');
        }

        $headerSize = 8 + 6 * $count;
        $properties = '';
        $propertyOffsets = [];
        $cache = [];
        foreach ($events as $event) {
            if ($event === null) {
                $propertyOffsets[] = 0;

                continue;
            }
            $paragraph = $event['paragraph'];
            $key = serialize($paragraph);
            if (!isset($cache[$key])) {
                $relative = $headerSize + strlen($properties);
                if ($relative > 0xFFFF) {
                    throw new RuntimeException('FDPP property offsets exceed the 16-bit Works limit.');
                }
                $cache[$key] = $relative;
                $properties .= $this->paragraphProperty($paragraph);
            }
            $propertyOffsets[] = $cache[$key];
        }

        $data = $this->u16($count) . $this->u16(0);
        foreach (array_keys($events) as $position) {
            $data .= $this->u32($position);
        }
        $data .= $this->u32($fullTextEnd);
        foreach ($propertyOffsets as $propertyOffset) {
            $data .= $this->u16($propertyOffset);
        }
        $data .= $properties;

        return $data;
    }

    private function objectFontProperty(): string
    {
        // FPROP size(8), main block value(0), child id=0/type=0x12/value=2;
        // WPS8TextStyle::FontData::T_Object == 2.
        return $this->u16(8)
            . $this->u16(0)
            . $this->u16(0x1200)
            . chr(2) . chr(0);
    }

    private function fontProperty(array $font, int $fontId): string
    {
        $main = $this->u16(0);
        if (!empty($font['bold'])) {
            $main .= $this->dataBoolTrue(0x02);
        }
        if (!empty($font['italic'])) {
            $main .= $this->dataBoolTrue(0x03);
        }
        $main .= $this->data32(0x0C, 0x22, (int) $font['size'] * 12700);
        if ((int) $font['underline'] !== 0) {
            $main .= $this->data16(0x1E, 0x12, (int) $font['underline']);
        }
        $main .= $this->fontArrayProperty($fontId);
        $main .= $this->data32(0x2E, 0x22, $this->rgbValue((string) $font['color']));

        return $this->record($main);
    }

    private function paragraphProperty(array $paragraph): string
    {
        $main = $this->u16(0)
            . $this->data16(0x04, 0x12, (int) $paragraph['alignment']);

        return $this->record($main);
    }

    private function fontArrayProperty(int $fontId): string
    {
        if ($fontId < 0 || $fontId > 255) {
            throw new RuntimeException('Works basic font selector is limited to 256 font-table entries.');
        }
        $nested = $this->u16(0) . $this->data16(0, 0x18, $fontId);
        $extraSize = 2 + strlen($nested);

        return $this->u16((0x8A << 8) | 0x24)
            . $this->u16($extraSize)
            . $nested;
    }

    private function encodeFontTable(array $fontNames): string
    {
        if (count($fontNames) > 256) {
            throw new RuntimeException('Works basic FONT table supports at most 256 selected font names.');
        }
        $records = '';
        $offsets = '';
        $recordBase = 20 + 4 * count($fontNames);
        foreach ($fontNames as $name) {
            $offsets .= $this->u32($recordBase + strlen($records));
            $records .= $this->fontNameRecord((string) $name);
        }
        $payload = $offsets . $records;

        return $this->u32(strlen($payload))
            . $this->u32(count($fontNames))
            . $this->u32(0) . $this->u32(0) . $this->u32(0)
            . $payload;
    }

    private function fontNameRecord(string $name): string
    {
        $length = strlen($name);
        if ($length < 1 || $length > 255 || preg_match('/^[\\x20-\\x7E]+$/D', $name) !== 1) {
            throw new RuntimeException('FONT table received an unrepresentable font name.');
        }
        $data = $this->u16($length);
        for ($i = 0; $i < $length; ++$i) {
            $data .= $this->u16(ord($name[$i]));
        }

        return $data . "\0\0\0\0";
    }

    private function rgbValue(string $hex): int
    {
        $hex = strtoupper(ltrim($hex, '#'));
        if (!preg_match('/^[0-9A-F]{6}$/D', $hex)) {
            throw new RuntimeException('Invalid RGB font color.');
        }
        $r = hexdec(substr($hex, 0, 2));
        $g = hexdec(substr($hex, 2, 2));
        $b = hexdec(substr($hex, 4, 2));

        return $r | ($g << 8) | ($b << 16);
    }

    private function encodeEobj(array $objects): string
    {
        $count = count($objects);
        if ($count < 1) {
            return '';
        }

        $data = $this->u32($count) . $this->u32(0) . "\0\0\0\0";
        foreach ($objects as $object) {
            $data .= $this->u32((int) $object['textUnitOffset']);
        }
        $last = $objects[$count - 1];
        $data .= $this->u32((int) $last['textUnitOffset'] + 1);

        foreach ($objects as $object) {
            $main = $this->u16(0);
            $main .= $this->data16(0, 0x1A, (int) $object['objectType']);
            $main .= $this->data32(1, 0x22, (int) $object['widthEmu']);
            $main .= $this->data32(2, 0x22, (int) $object['heightEmu']);
            $main .= $this->data32(3, 0x22, (int) $object['objectId']);
            $data .= $this->record($main);
        }

        return $data;
    }

    private function encodeStrs(int $mainUnits, array $tables): string
    {
        $count = 1 + count($tables);
        $data = $this->u32($count) . $this->u32(0) . "\0\0\0\0";

        // STRS is a P_MINCR PLC: each pointer value is the UTF-16 length of
        // the current zone, followed by a zero-length sentinel increment.
        $data .= $this->u32((int) $mainUnits);
        foreach ($tables as $table) {
            $data .= $this->u32((int) $table['zoneUnits']);
        }
        $data .= $this->u32(0);

        $data .= $this->structuredRecord([$this->data32(0, 0x22, 1)]); // Main
        foreach ($tables as $table) {
            $data .= $this->structuredRecord([$this->data32(0, 0x22, 5)]); // Table/section auxiliary text
        }

        return $data;
    }

    private function encodeTcd(array $cellEndUnitOffsets): string
    {
        $count = count($cellEndUnitOffsets);
        if ($count < 1) {
            throw new RuntimeException('A TCD table must contain at least one cell boundary.');
        }

        $data = $this->u32($count) . $this->u32(0) . "\0\0\0\0";
        $previous = -1;
        foreach ($cellEndUnitOffsets as $offset) {
            $offset = (int) $offset;
            if ($offset <= $previous) {
                throw new RuntimeException('TCD cell boundaries must be strictly increasing.');
            }
            $data .= $this->u32($offset);
            $previous = $offset;
        }
        // PLC sentinel. libwps ignores the final interval as data, but requires
        // N+1 positions. Repeating the final end is the canonical minimal form.
        $data .= $this->u32((int) end($cellEndUnitOffsets));

        return $data;
    }

    private function encodeFram(array $tables): string
    {
        $data = $this->u16(count($tables));
        foreach ($tables as $table) {
            $children = '';
            $children .= $this->data16(1, 0x12, 12); // Frame::Table
            $children .= $this->dataArray3(0x11, (int) $table['objectId'], 0, 0);
            $children .= $this->data32(0x18, 0x22, (int) $table['strsId']);
            $children .= $this->data32(0x2A, 0x22, (int) $table['tableId']);
            $data .= $this->structuredRecord([$children]);
        }

        return $data;
    }

    private function encodeMcld(array $tables): string
    {
        $data = $this->u32(0) . $this->u32(count($tables));
        foreach ($tables as $table) {
            $data .= $this->u32((int) $table['tableId']);
        }

        foreach ($tables as $table) {
            // Minimal table-level block accepted by WPS8Table::readMCLD.
            $data .= $this->structuredRecord([]);
            $data .= $this->u32(count($table['cells']));
            foreach ($table['cells'] as $cell) {
                $children = '';
                $children .= $this->data32(0, 0x22, (int) $cell['topEmu']);
                $children .= $this->data32(1, 0x22, (int) $cell['leftEmu']);
                $children .= $this->data32(2, 0x22, (int) $cell['bottomEmu']);
                $children .= $this->data32(3, 0x22, (int) $cell['rightEmu']);
                $children .= $this->data32(4, 0x22, (int) $cell['widthEmu']);
                $children .= $this->data32(5, 0x22, (int) $cell['heightEmu']);
                $data .= $this->structuredRecord([$children]);
            }
        }

        return $data;
    }

    private function structuredRecord(array $children): string
    {
        $main = $this->u16(0) . implode('', $children);

        return $this->record($main);
    }

    private function record(string $main): string
    {
        return $this->u16(2 + strlen($main)) . $main;
    }

    private function dataArray3(int $id, int $a, int $b, int $c): string
    {
        // type 0x82: extraSize includes tag+size+payload and the nested block
        // starts with a two-byte main value before the three int32 values.
        return $this->u16((0x82 << 8) | ($id & 0xFF))
            . $this->u16(16)
            . $this->u16(0)
            . $this->u32($a) . $this->u32($b) . $this->u32($c);
    }

    private function dataBoolTrue(int $id): string
    {
        // Works bool true uses low-level type 0x0A; FileData::type() normalizes
        // it to 0x02, which is what the style type maps expect.
        return $this->u16((0x0A << 8) | ($id & 0xFF));
    }

    private function normalizeRuns(array $runs, string $key): array
    {
        usort($runs, static function ($a, $b): int {
            $cmp = ((int) $a['startUnit']) <=> ((int) $b['startUnit']);

            return $cmp !== 0 ? $cmp : ((int) $a['endUnit']) <=> ((int) $b['endUnit']);
        });
        $out = [];
        $lastEnd = -1;
        foreach ($runs as $run) {
            $start = (int) $run['startUnit'];
            $end = (int) $run['endUnit'];
            if ($start < 0 || $end <= $start || !isset($run[$key])) {
                throw new RuntimeException('Invalid Works style run.');
            }
            if ($start < $lastEnd) {
                throw new RuntimeException('Overlapping Works style runs are outside the deterministic subset.');
            }
            $last = count($out) - 1;
            if ($last >= 0 && $out[$last]['endUnit'] === $start && $out[$last][$key] === $run[$key]) {
                $out[$last]['endUnit'] = $end;
            } else {
                $run['startUnit'] = $start;
                $run['endUnit'] = $end;
                $out[] = $run;
            }
            $lastEnd = $end;
        }

        return $out;
    }

    private function data16(int $id, int $type, int $value): string
    {
        return $this->u16((($type & 0xFF) << 8) | ($id & 0xFF)) . $this->u16($value);
    }

    private function data32(int $id, int $type, int $value): string
    {
        return $this->u16((($type & 0xFF) << 8) | ($id & 0xFF)) . $this->u32($value);
    }

    private function indexRegionSize(int $zoneCount): int
    {
        if ($zoneCount < 1 || $zoneCount > 65535) {
            throw new RuntimeException('Invalid Works zone count.');
        }
        $remaining = $zoneCount;
        $size = 0x18;
        while ($remaining > 0) {
            $local = min(0x20, $remaining);
            $size += 8 + 24 * $local;
            $remaining -= $local;
        }

        return $size;
    }

    private function encodeIndexRegion(array $zones): string
    {
        $zoneCount = count($zones);
        $data = 'CHNKWKS' . "\0";
        $data .= $this->i16(0) . $this->i16(0) . $this->u16($zoneCount);
        $data .= $this->u16(0) . $this->u16(0) . $this->u16(0) . $this->u16(0) . $this->u16(0);

        $blocks = array_chunk($zones, 0x20);
        $blockStart = 0x18;
        foreach ($blocks as $blockIndex => $block) {
            $blockSize = 8 + 24 * count($block);
            $next = ($blockIndex + 1 < count($blocks)) ? $blockStart + $blockSize : 0xFFFFFFFF;
            $data .= $this->u16(0) . $this->u16(count($block)) . $this->u32($next);
            foreach ($block as $zone) {
                $data .= $this->indexEntry($zone['name'], $zone['type'], $zone['id'], $zone['offset'], $zone['length']);
            }
            $blockStart += $blockSize;
        }

        return $data;
    }

    private function indexEntry(string $name, string $type, int $id, int $offset, int $length): string
    {
        if (strlen($name) !== 4 || strlen($type) !== 4) {
            throw new InvalidArgumentException('WPS zone names and types must be exactly four bytes.');
        }

        return $this->u16(0x18) . $name . $this->u16($id)
            . $this->i16(0) . $this->i16(0) . $type
            . $this->u32($offset) . $this->u32($length);
    }

    private function normalizeText(string $text): string
    {
        $text = str_replace(["\r\n", "\n"], "\r", (string) $text);

        return str_replace("\0", '', $text);
    }

    private function u16(int $value): string
    {
        return pack('v', $value & 0xFFFF);
    }

    private function i16(int $value): string
    {
        return pack('v', $value & 0xFFFF);
    }

    private function u32(int $value): string
    {
        return pack('V', $value & 0xFFFFFFFF);
    }
}
