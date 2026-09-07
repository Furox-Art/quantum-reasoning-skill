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

use RuntimeException;
use Throwable;

/**
 * Independent deterministic validator for the exact subset emitted by WPS.
 *
 * It reparses CFB, Works index chains, TEXT/STRS subdivisions, FDPC, EOBJ,
 * image Ole10Native payloads, and the table TCD/FRAM/MCLD graph. Validation
 * does not consume writer-side offsets/hashes as authoritative facts.
 */
final class Validator
{
    private const FREESECT = 0xFFFFFFFF;
    private const ENDOFCHAIN = 0xFFFFFFFE;
    private const FATSECT = 0xFFFFFFFD;
    private const NOSTREAM = 0xFFFFFFFF;

    /**
     * @param string       $filename
     * @param array|string $expected string for legacy text-only validation, or
     *                              ['text'=>string,'images'=>array,'tables'=>array]
     */
    public function validateFile($filename, $expected = null): array
    {
        $bytes = @file_get_contents($filename);
        if ($bytes === false) {
            return $this->failure('Cannot read output file.');
        }

        try {
            $cfb = $this->parseCfb($bytes);
            $contentsEntry = $this->findEntryByNameAndType($cfb['directory'], 'CONTENTS', 2);
            if ($contentsEntry === null) {
                throw new RuntimeException('CFB CONTENTS stream was not found.');
            }
            if ($contentsEntry['size'] < 4096) {
                throw new RuntimeException('Mini Stream CONTENTS is outside the supported writer subset.');
            }

            $contents = $this->readChain($bytes, $cfb['fat'], $contentsEntry['start'], $contentsEntry['size']);
            $works = $this->parseContents($contents);
            $errors = [];

            $expectedText = null;
            $expectedImages = [];
            $expectedTables = [];
            $expectedStyles = ['fontRuns' => [], 'paragraphRuns' => []];
            if (is_array($expected)) {
                $expectedText = array_key_exists('text', $expected) ? (string) $expected['text'] : null;
                $expectedImages = isset($expected['images']) && is_array($expected['images']) ? $expected['images'] : [];
                $expectedTables = isset($expected['tables']) && is_array($expected['tables']) ? $expected['tables'] : [];
                if (isset($expected['styles']) && is_array($expected['styles'])) {
                    $expectedStyles['fontRuns'] = isset($expected['styles']['fontRuns']) && is_array($expected['styles']['fontRuns']) ? $expected['styles']['fontRuns'] : [];
                    $expectedStyles['paragraphRuns'] = isset($expected['styles']['paragraphRuns']) && is_array($expected['styles']['paragraphRuns']) ? $expected['styles']['paragraphRuns'] : [];
                }
            } elseif ($expected !== null) {
                $expectedText = (string) $expected;
            }

            if ($expectedText !== null && $works['text'] !== $expectedText) {
                $errors[] = 'Main TEXT zone does not exactly match the expected document projection.';
            }

            $fontNames = $this->parseFontTable($contents, $this->firstZone($works['zoneLists'], 'FONT'));
            $expectedStyleRuns = $this->flattenExpectedStyles($expectedText ?? $works['text'], $expectedTables, $expectedStyles);
            $fdpcZone = $this->firstZone($works['zoneLists'], 'FDPC');
            $parsedFdpc = ['objects' => [], 'fontRuns' => []];
            $needFdpc = count($expectedImages) + count($expectedTables) > 0 || $expectedStyleRuns['fontRuns'] !== [];
            if ($needFdpc) {
                if ($fdpcZone === null || $fdpcZone['type'] !== 'FDPC') {
                    $errors[] = 'Missing FDPC zone required for inline objects or character styles.';
                } else {
                    $parsedFdpc = $this->parseFdpc($contents, $fdpcZone, $works['textZone'], $fontNames);
                }
            } elseif ($fdpcZone !== null) {
                $errors[] = 'Unexpected FDPC zone is present in a projection without objects or character styles.';
            }

            $actualParagraphRuns = [];
            $fdppZone = $this->firstZone($works['zoneLists'], 'FDPP');
            if ($expectedStyleRuns['paragraphRuns'] !== []) {
                if ($fdppZone === null || $fdppZone['type'] !== 'FDPP') {
                    $errors[] = 'Missing FDPP zone required for paragraph styles.';
                } else {
                    $actualParagraphRuns = $this->parseFdpp($contents, $fdppZone, $works['textZone']);
                }
            } elseif ($fdppZone !== null) {
                $errors[] = 'Unexpected FDPP zone is present in a projection without paragraph styles.';
            }

            $this->compareStyleRuns($parsedFdpc['fontRuns'], $expectedStyleRuns['fontRuns'], 'character', $errors);
            $this->compareStyleRuns($actualParagraphRuns, $expectedStyleRuns['paragraphRuns'], 'paragraph', $errors);

            $expectedObjects = count($expectedImages) + count($expectedTables);
            $eobjRecords = [];
            $fdpcObjects = $parsedFdpc['objects'];
            if ($expectedObjects > 0) {
                $eobjZone = $this->firstZone($works['zoneLists'], 'EOBJ');
                if ($eobjZone === null || $eobjZone['type'] !== 'PLC ') {
                    $errors[] = 'Missing EOBJ PLC zone required for inline objects.';
                } else {
                    $eobjRecords = $this->parseEobj($contents, $eobjZone);
                    if (count($eobjRecords) !== $expectedObjects) {
                        $errors[] = 'EOBJ object count does not match the expected inline-object count.';
                    }
                }
            } elseif (is_array($expected) && $this->firstZone($works['zoneLists'], 'EOBJ') !== null) {
                $errors[] = 'Unexpected EOBJ zone is present in an object-free projection.';
            }

            $validatedImages = $this->validateImages(
                $bytes,
                $cfb,
                $works,
                $expectedImages,
                $fdpcObjects,
                $eobjRecords,
                $errors
            );
            $validatedTables = $this->validateTables(
                $contents,
                $works,
                $expectedTables,
                $fdpcObjects,
                $eobjRecords,
                $errors
            );

            return [
                'valid' => $errors === [],
                'errors' => $errors,
                'text' => $works['text'],
                'images' => $validatedImages,
                'tables' => $validatedTables,
                'styles' => [
                    'fontRuns' => $parsedFdpc['fontRuns'],
                    'paragraphRuns' => $actualParagraphRuns,
                    'fontNames' => $fontNames,
                ],
            ];
        } catch (Throwable $e) {
            return $this->failure($e->getMessage());
        }
    }

    private function failure(string $message): array
    {
        return [
            'valid' => false,
            'errors' => [$message],
            'text' => null,
            'images' => [],
            'tables' => [],
            'styles' => ['fontRuns' => [], 'paragraphRuns' => [], 'fontNames' => []],
        ];
    }

    private function parseCfb(string $file): array
    {
        if (strlen($file) < 512 || substr($file, 0, 8) !== "\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1") {
            throw new RuntimeException('Invalid CFB signature.');
        }
        if ($this->u16($file, 28) !== 0xFFFE || $this->u16($file, 30) !== 9) {
            throw new RuntimeException('Unsupported CFB byte order or sector size.');
        }
        if ($this->u32($file, 56) !== 4096) {
            throw new RuntimeException('Unexpected CFB Mini Stream cutoff.');
        }

        $fatCount = $this->u32($file, 44);
        $firstDirectory = $this->u32($file, 48);
        if ($fatCount < 1 || $fatCount > 109) {
            throw new RuntimeException('Invalid or unsupported FAT count.');
        }

        $fat = [];
        for ($i = 0; $i < $fatCount; ++$i) {
            $fatSector = $this->u32($file, 76 + 4 * $i);
            if ($fatSector === self::FREESECT) {
                throw new RuntimeException('Missing FAT sector in DIFAT.');
            }
            $sector = $this->sector($file, $fatSector);
            for ($j = 0; $j < 128; ++$j) {
                $fat[] = $this->u32($sector, $j * 4);
            }
        }

        $directoryBytes = $this->readChain($file, $fat, $firstDirectory, null);
        $directory = [];
        for ($offset = 0, $index = 0; $offset + 128 <= strlen($directoryBytes); $offset += 128, ++$index) {
            $nameLength = $this->u16($directoryBytes, $offset + 64);
            $type = ord($directoryBytes[$offset + 66]);
            if ($type === 0 && $nameLength === 0) {
                $directory[$index] = [
                    'index' => $index, 'name' => '', 'type' => 0,
                    'left' => self::NOSTREAM, 'right' => self::NOSTREAM, 'child' => self::NOSTREAM,
                    'start' => self::ENDOFCHAIN, 'size' => 0,
                ];

                continue;
            }
            if ($nameLength < 2 || $nameLength > 64 || ($nameLength % 2) !== 0) {
                throw new RuntimeException('Invalid CFB directory name length at entry ' . $index . '.');
            }
            $name = Utf16::decodeLe(substr($directoryBytes, $offset, $nameLength - 2));
            $directory[$index] = [
                'index' => $index,
                'name' => $name,
                'type' => $type,
                'left' => $this->u32($directoryBytes, $offset + 68),
                'right' => $this->u32($directoryBytes, $offset + 72),
                'child' => $this->u32($directoryBytes, $offset + 76),
                'start' => $this->u32($directoryBytes, $offset + 116),
                'size' => $this->u64($directoryBytes, $offset + 120),
            ];
        }

        if (!isset($directory[0]) || $directory[0]['type'] !== 5 || $directory[0]['name'] !== 'Root Entry') {
            throw new RuntimeException('Invalid CFB root directory entry.');
        }

        return ['fat' => $fat, 'directory' => $directory];
    }

    private function parseContents(string $contents): array
    {
        if (strlen($contents) < 0x50 || substr($contents, 0, 7) !== 'CHNKWKS') {
            throw new RuntimeException('Invalid Works 7/8 CONTENTS magic.');
        }
        $entryCount = $this->u16($contents, 0x0C);
        if ($entryCount < 2) {
            throw new RuntimeException('Works CONTENTS index is incomplete.');
        }

        $pos = 0x18;
        $remaining = $entryCount;
        $zoneLists = [];
        $allZones = [];
        $guard = 0;
        while ($remaining > 0) {
            if (++$guard > 256 || $pos + 8 > strlen($contents)) {
                throw new RuntimeException('Invalid Works index chain.');
            }
            $localCount = $this->u16($contents, $pos + 2);
            $next = $this->u32($contents, $pos + 4);
            if ($localCount < 1 || $localCount > 0x20 || $localCount > $remaining) {
                throw new RuntimeException('Invalid Works local index count.');
            }
            $entryPos = $pos + 8;
            for ($i = 0; $i < $localCount; ++$i, --$remaining) {
                if ($entryPos + 24 > strlen($contents)) {
                    throw new RuntimeException('Truncated Works index entry.');
                }
                $size = $this->u16($contents, $entryPos);
                if ($size < 24 || $entryPos + $size > strlen($contents)) {
                    throw new RuntimeException('Invalid Works index entry size.');
                }
                $name = substr($contents, $entryPos + 2, 4);
                $zone = [
                    'name' => $name,
                    'id' => $this->u16($contents, $entryPos + 6),
                    'type' => substr($contents, $entryPos + 12, 4),
                    'begin' => $this->u32($contents, $entryPos + 16),
                    'length' => $this->u32($contents, $entryPos + 20),
                ];
                if ($zone['begin'] + $zone['length'] > strlen($contents)) {
                    throw new RuntimeException('Works zone points outside CONTENTS.');
                }
                $zoneLists[$name][] = $zone;
                $allZones[] = $zone;
                $entryPos += $size;
            }

            if ($remaining === 0) {
                break;
            }
            if ($next === self::FREESECT || $next <= $pos) {
                throw new RuntimeException('Works index ended or moved backwards before all entries were read.');
            }
            $pos = $next;
        }

        $font = $this->firstZone($zoneLists, 'FONT');
        $textZone = $this->firstZone($zoneLists, 'TEXT');
        if ($font === null || $font['type'] !== 'FONT' || $font['length'] < 20) {
            throw new RuntimeException('Missing or invalid required Works FONT zone.');
        }
        if ($textZone === null || $textZone['type'] !== 'TEXT' || ($textZone['length'] % 2) !== 0) {
            throw new RuntimeException('Missing or invalid required Works TEXT zone.');
        }
        if (count($zoneLists['FONT']) !== 1 || count($zoneLists['TEXT']) !== 1) {
            throw new RuntimeException('Duplicate FONT/TEXT zones are outside the emitted subset.');
        }

        $textBytes = substr($contents, $textZone['begin'], $textZone['length']);
        $textZones = [[
            'vectorIndex' => 0,
            'typeId' => 1,
            'beginUnit' => 0,
            'endUnit' => intdiv(strlen($textBytes), 2),
        ]];

        $strs = $this->firstZone($zoneLists, 'STRS');
        if ($strs !== null) {
            if ($strs['type'] !== 'PLC ' || count($zoneLists['STRS']) !== 1) {
                throw new RuntimeException('Invalid or duplicate STRS zone.');
            }
            $textZones = $this->parseStrs($contents, $strs, intdiv(strlen($textBytes), 2));
        }

        $main = null;
        foreach ($textZones as $zone) {
            if ($zone['typeId'] === 1) {
                if ($main !== null) {
                    throw new RuntimeException('Multiple main text subdivisions are outside the emitted subset.');
                }
                $main = $zone;
            }
        }
        if ($main === null) {
            throw new RuntimeException('STRS does not define a main text subdivision.');
        }

        $mainBytes = substr($textBytes, 2 * $main['beginUnit'], 2 * ($main['endUnit'] - $main['beginUnit']));

        return [
            'zoneLists' => $zoneLists,
            'zones' => $allZones,
            'textZone' => $textZone,
            'textBytes' => $textBytes,
            'textZones' => $textZones,
            'text' => Utf16::decodeLe($mainBytes),
        ];
    }

    private function parseStrs(string $contents, array $zone, int $totalTextUnits): array
    {
        $data = substr($contents, $zone['begin'], $zone['length']);
        if (strlen($data) < 24) {
            throw new RuntimeException('STRS zone is too short.');
        }
        $count = $this->u32($data, 0);
        $dataSize = $this->u32($data, 4);
        if ($count < 1 || $count > 1000 || $dataSize !== 0) {
            throw new RuntimeException('Invalid STRS PLC header.');
        }
        $offset = 12;
        if ($offset + 4 * ($count + 1) > strlen($data)) {
            throw new RuntimeException('Truncated STRS pointer table.');
        }
        $increments = [];
        for ($i = 0; $i <= $count; ++$i) {
            $increments[] = $this->u32($data, $offset);
            $offset += 4;
        }
        if ($increments[$count] !== 0) {
            throw new RuntimeException('STRS final incremental sentinel is not zero.');
        }

        $zones = [];
        $beginUnit = 0;
        for ($i = 0; $i < $count; ++$i) {
            $record = $this->parseStructuredRecord($data, $offset, [0x22]);
            $offset = $record['end'];
            if (!isset($record['values'][0])) {
                throw new RuntimeException('STRS record does not contain a text-zone type.');
            }
            $endUnit = $beginUnit + (int) $increments[$i];
            if ($endUnit < $beginUnit || $endUnit > $totalTextUnits) {
                throw new RuntimeException('STRS text subdivision is outside TEXT.');
            }
            $zones[] = [
                'vectorIndex' => $i,
                'typeId' => (int) $record['values'][0],
                'beginUnit' => $beginUnit,
                'endUnit' => $endUnit,
            ];
            $beginUnit = $endUnit;
        }
        if ($offset !== strlen($data) || $beginUnit !== $totalTextUnits) {
            throw new RuntimeException('STRS subdivisions do not exactly consume the TEXT zone.');
        }

        return $zones;
    }

    private function validateImages(string $file, array $cfb, array $works, array $expectedImages, array $fdpcObjects, array $eobjRecords, array &$errors): array
    {
        if ($expectedImages === []) {
            return [];
        }

        $eobjById = [];
        foreach ($eobjRecords as $record) {
            $eobjById[$record['objectId']] = $record;
        }
        $textBegin = $works['textZone']['begin'];
        $validated = [];

        foreach ($expectedImages as $expected) {
            $objectId = (int) $expected['objectId'];
            $textUnitOffset = (int) $expected['textUnitOffset'];
            $absoluteTextByte = $textBegin + 2 * $textUnitOffset;
            if (!isset($fdpcObjects[$absoluteTextByte]) || $fdpcObjects[$absoluteTextByte] !== 2) {
                $errors[] = 'FDPC does not mark image object ' . $objectId . ' at the exact TEXT position.';
            }

            if (!isset($eobjById[$objectId])) {
                $errors[] = 'Missing EOBJ record for image object ' . $objectId . '.';

                continue;
            }
            $actual = $eobjById[$objectId];
            $this->compareObjectRecord($actual, $expected, 2, 'image', $errors);

            $payload = $this->readObjectPayload($file, $cfb, $objectId);
            $expectedBinary = (string) $expected['binary'];
            $actualHash = hash('sha256', $payload);
            $expectedHash = hash('sha256', $expectedBinary);
            if (strlen($payload) !== strlen($expectedBinary) || !hash_equals($expectedHash, $actualHash) || $payload !== $expectedBinary) {
                $errors[] = 'Ole10Native payload is not byte-for-byte identical for image object ' . $objectId . '.';
            }

            $validated[] = [
                'objectId' => $objectId,
                'textUnitOffset' => $actual['textUnitOffset'],
                'widthEmu' => $actual['widthEmu'],
                'heightEmu' => $actual['heightEmu'],
                'byteLength' => strlen($payload),
                'sha256' => $actualHash,
            ];
        }

        return $validated;
    }

    private function validateTables(string $contents, array $works, array $expectedTables, array $fdpcObjects, array $eobjRecords, array &$errors): array
    {
        if ($expectedTables === []) {
            if ($this->firstZone($works['zoneLists'], 'MCLD') !== null || $this->firstZone($works['zoneLists'], 'FRAM') !== null || isset($works['zoneLists']['TCD '])) {
                $errors[] = 'Unexpected table-specific zones are present in a table-free projection.';
            }

            return [];
        }

        $strs = $this->firstZone($works['zoneLists'], 'STRS');
        $framZone = $this->firstZone($works['zoneLists'], 'FRAM');
        $mcldZone = $this->firstZone($works['zoneLists'], 'MCLD');
        if ($strs === null || $framZone === null || $mcldZone === null) {
            $errors[] = 'Missing STRS/FRAM/MCLD zone required for Works tables.';

            return [];
        }
        if ($framZone['type'] !== 'FRAM' || $mcldZone['type'] !== 'MCLD') {
            $errors[] = 'FRAM/MCLD table zone has the wrong Works type.';

            return [];
        }
        if (count($works['zoneLists']['FRAM']) !== 1 || count($works['zoneLists']['MCLD']) !== 1) {
            $errors[] = 'Duplicate FRAM/MCLD zones are outside the emitted subset.';

            return [];
        }

        $frames = $this->parseFram($contents, $framZone);
        $mcld = $this->parseMcld($contents, $mcldZone);
        $eobjById = [];
        foreach ($eobjRecords as $record) {
            $eobjById[$record['objectId']] = $record;
        }
        $frameByObject = [];
        foreach ($frames as $frame) {
            $frameByObject[$frame['objectId']] = $frame;
        }
        $mcldById = [];
        foreach ($mcld as $table) {
            $mcldById[$table['tableId']] = $table;
        }

        if (count($frames) !== count($expectedTables) || count($mcld) !== count($expectedTables)) {
            $errors[] = 'FRAM/MCLD table count does not match the expected table count.';
        }

        $validated = [];
        foreach ($expectedTables as $expected) {
            $objectId = (int) $expected['objectId'];
            $tableId = (int) $expected['tableId'];
            $strsId = (int) $expected['strsId'];
            $textUnitOffset = (int) $expected['textUnitOffset'];
            $absoluteTextByte = $works['textZone']['begin'] + 2 * $textUnitOffset;
            if (!isset($fdpcObjects[$absoluteTextByte]) || $fdpcObjects[$absoluteTextByte] !== 2) {
                $errors[] = 'FDPC does not mark table object ' . $objectId . ' at the exact TEXT position.';
            }

            if (!isset($eobjById[$objectId])) {
                $errors[] = 'Missing EOBJ record for table object ' . $objectId . '.';

                continue;
            }
            $this->compareObjectRecord($eobjById[$objectId], $expected, 3, 'table', $errors);

            if (!isset($frameByObject[$objectId])) {
                $errors[] = 'FRAM does not link table object ' . $objectId . '.';
            } else {
                $frame = $frameByObject[$objectId];
                if ($frame['frameType'] !== 12 || $frame['strsId'] !== $strsId || $frame['tableId'] !== $tableId) {
                    $errors[] = 'FRAM object/STRS/MCLD linkage mismatch for table object ' . $objectId . '.';
                }
            }

            if (!isset($works['textZones'][$strsId]) || $works['textZones'][$strsId]['typeId'] !== 5) {
                $errors[] = 'STRS does not define expected type-5 text zone ' . $strsId . ' for table ' . $tableId . '.';

                continue;
            }
            $textSubdivision = $works['textZones'][$strsId];
            $actualZoneUnits = $textSubdivision['endUnit'] - $textSubdivision['beginUnit'];
            if ($actualZoneUnits !== (int) $expected['zoneUnits']) {
                $errors[] = 'STRS table text-zone length mismatch for table ' . $tableId . '.';
            }

            $tcdZone = $this->findZoneById($works['zoneLists'], 'TCD ', $strsId);
            if ($tcdZone === null || $tcdZone['type'] !== 'PLC ') {
                $errors[] = 'TCD cell-boundary zone is missing for table ' . $tableId . '.';

                continue;
            }
            $cellEnds = $this->parseTcd($contents, $tcdZone);
            $expectedEnds = array_map('intval', $expected['cellEndUnitOffsets']);
            if ($cellEnds !== $expectedEnds) {
                $errors[] = 'TCD cell boundaries do not exactly match for table ' . $tableId . '.';
            }

            if (!isset($mcldById[$tableId])) {
                $errors[] = 'MCLD table definition ' . $tableId . ' is missing.';

                continue;
            }
            $actualTable = $mcldById[$tableId];
            if (count($actualTable['cells']) !== count($expected['cells'])) {
                $errors[] = 'MCLD cell count mismatch for table ' . $tableId . '.';
            }

            $logicalTexts = $this->decodeTableCells($works['textBytes'], $textSubdivision, $cellEnds, $errors, $tableId);
            $validatedCells = [];
            foreach ($expected['cells'] as $index => $expectedCell) {
                if (!isset($actualTable['cells'][$index])) {
                    continue;
                }
                $actualCell = $actualTable['cells'][$index];
                foreach (['topEmu', 'leftEmu', 'bottomEmu', 'rightEmu', 'widthEmu', 'heightEmu'] as $key) {
                    if ((int) $actualCell[$key] !== (int) $expectedCell[$key]) {
                        $errors[] = 'MCLD ' . $key . ' mismatch for table ' . $tableId . ', cell ' . $index . '.';
                    }
                }
                $actualText = $logicalTexts[$index] ?? null;
                if ($actualText !== (string) $expectedCell['text']) {
                    $errors[] = 'Cell text mismatch for table ' . $tableId . ', cell ' . $index . '.';
                }
                $validatedCells[] = array_merge($actualCell, ['text' => $actualText]);
            }

            $derivedRows = 0;
            $derivedColumns = 0;
            foreach ($expected['cells'] as $expectedCell) {
                if (isset($expectedCell['row'])) {
                    $derivedRows = max($derivedRows, (int) $expectedCell['row'] + 1);
                }
                if (isset($expectedCell['column'])) {
                    $derivedColumns = max($derivedColumns, (int) $expectedCell['column'] + 1);
                }
            }

            $validated[] = [
                'objectId' => $objectId,
                'tableId' => $tableId,
                'strsId' => $strsId,
                'textUnitOffset' => $eobjById[$objectId]['textUnitOffset'],
                'widthEmu' => $eobjById[$objectId]['widthEmu'],
                'heightEmu' => $eobjById[$objectId]['heightEmu'],
                'rows' => isset($expected['rows']) ? (int) $expected['rows'] : $derivedRows,
                'columns' => isset($expected['columns']) ? (int) $expected['columns'] : $derivedColumns,
                'cells' => $validatedCells,
            ];
        }

        return $validated;
    }

    private function compareObjectRecord(array $actual, array $expected, int $expectedType, string $label, array &$errors): void
    {
        $id = (int) $expected['objectId'];
        if ($actual['textUnitOffset'] !== (int) $expected['textUnitOffset']) {
            $errors[] = 'EOBJ text position mismatch for ' . $label . ' object ' . $id . '.';
        }
        if ($actual['type'] !== $expectedType) {
            $errors[] = 'EOBJ object type mismatch for ' . $label . ' object ' . $id . '.';
        }
        if ($actual['objectId'] !== $id) {
            $errors[] = 'EOBJ object identifier mismatch for ' . $label . ' object ' . $id . '.';
        }
        if ($actual['widthEmu'] !== (int) $expected['widthEmu'] || $actual['heightEmu'] !== (int) $expected['heightEmu']) {
            $errors[] = 'EOBJ physical dimensions mismatch for ' . $label . ' object ' . $id . '.';
        }
    }

    private function parseFontTable(string $contents, ?array $zone): array
    {
        if ($zone === null || $zone['type'] !== 'FONT') {
            throw new RuntimeException('Missing Works FONT table.');
        }
        $data = substr($contents, $zone['begin'], $zone['length']);
        if (strlen($data) < 20) {
            throw new RuntimeException('FONT table is too short.');
        }
        $payloadLength = $this->u32($data, 0);
        $count = $this->u32($data, 4);
        if ($count > 256 || $payloadLength + 20 !== strlen($data) || 20 + 4 * $count > strlen($data)) {
            throw new RuntimeException('Invalid Works FONT table header.');
        }
        $offsets = [];
        $pos = 20;
        for ($i = 0; $i < $count; ++$i) {
            $offsets[] = $this->u32($data, $pos);
            $pos += 4;
        }
        $names = [];
        for ($i = 0; $i < $count; ++$i) {
            $expectedPos = $pos;
            if ($offsets[$i] !== $expectedPos) {
                throw new RuntimeException('FONT record offset table is inconsistent.');
            }
            if ($pos + 2 > strlen($data)) {
                throw new RuntimeException('Truncated FONT name record.');
            }
            $length = $this->u16($data, $pos);
            $pos += 2;
            if ($length < 1 || $length > 255 || $pos + 2 * $length + 4 > strlen($data)) {
                throw new RuntimeException('Invalid FONT name length.');
            }
            $name = '';
            for ($j = 0; $j < $length; ++$j) {
                $code = $this->u16($data, $pos);
                $pos += 2;
                if ($code < 0x20 || $code > 0x7E) {
                    throw new RuntimeException('FONT name is outside the emitted ASCII subset.');
                }
                $name .= chr($code);
            }
            $pos += 4; // unknown bytes retained as zero by the writer
            $names[] = $name;
        }
        if ($pos !== strlen($data)) {
            throw new RuntimeException('Unexpected trailing bytes in FONT table.');
        }

        return $names;
    }

    private function flattenExpectedStyles(string $mainText, array $tables, array $styles): array
    {
        $fontRuns = $styles['fontRuns'] ?? [];
        $paragraphRuns = $styles['paragraphRuns'] ?? [];
        $base = intdiv(strlen(Utf16::encodeLe((string) $mainText)), 2);
        foreach ($tables as $table) {
            foreach (($table['fontRuns'] ?? []) as $run) {
                $run['startUnit'] = (int) $run['startUnit'] + $base;
                $run['endUnit'] = (int) $run['endUnit'] + $base;
                $fontRuns[] = $run;
            }
            foreach (($table['paragraphRuns'] ?? []) as $run) {
                $run['startUnit'] = (int) $run['startUnit'] + $base;
                $run['endUnit'] = (int) $run['endUnit'] + $base;
                $paragraphRuns[] = $run;
            }
            $base += (int) ($table['zoneUnits'] ?? 0);
        }

        return [
            'fontRuns' => $this->normalizeExpectedRuns($fontRuns, 'font'),
            'paragraphRuns' => $this->normalizeExpectedRuns($paragraphRuns, 'paragraph'),
        ];
    }

    private function normalizeExpectedRuns(array $runs, string $key): array
    {
        usort($runs, static function ($a, $b): int {
            $cmp = ((int) $a['startUnit']) <=> ((int) $b['startUnit']);

            return $cmp !== 0 ? $cmp : ((int) $a['endUnit']) <=> ((int) $b['endUnit']);
        });
        $out = [];
        foreach ($runs as $run) {
            if (!isset($run[$key])) {
                continue;
            }
            $run['startUnit'] = (int) $run['startUnit'];
            $run['endUnit'] = (int) $run['endUnit'];
            $last = count($out) - 1;
            if ($last >= 0 && $out[$last]['endUnit'] === $run['startUnit'] && $out[$last][$key] === $run[$key]) {
                $out[$last]['endUnit'] = $run['endUnit'];
            } else {
                $out[] = $run;
            }
        }

        return $out;
    }

    private function compareStyleRuns(array $actual, array $expected, string $kind, array &$errors): void
    {
        if ($actual === $expected) {
            return;
        }
        if (count($actual) !== count($expected)) {
            $errors[] = ucfirst($kind) . ' style run count mismatch.';

            return;
        }
        foreach ($expected as $i => $run) {
            if ($actual[$i] !== $run) {
                $errors[] = ucfirst($kind) . ' style mismatch at run ' . $i . '.';
            }
        }
    }

    private function parseFdpc(string $contents, array $zone, array $textZone, array $fontNames): array
    {
        $data = substr($contents, $zone['begin'], $zone['length']);
        $fod = $this->parseFodHeader($data, 'FDPC');
        $objects = [];
        $fontRuns = [];
        $textBegin = (int) $textZone['begin'];
        $textEnd = $textBegin + (int) $textZone['length'];
        if ($fod['positions'][count($fod['positions']) - 1] !== $textEnd) {
            throw new RuntimeException('FDPC final text boundary does not match TEXT.');
        }

        for ($i = 0; $i < $fod['count']; ++$i) {
            $start = $fod['positions'][$i];
            $end = $fod['positions'][$i + 1];
            if ($start < $textBegin || $end < $start || $end > $textEnd || (($start - $textBegin) % 2) !== 0 || (($end - $textBegin) % 2) !== 0) {
                throw new RuntimeException('FDPC style boundary is outside aligned TEXT bytes.');
            }
            $propertyOffset = $fod['propertyOffsets'][$i];
            if ($propertyOffset === 0) {
                continue;
            }
            $property = $this->parseFontProperty($data, $propertyOffset, $fontNames);
            $startUnit = intdiv($start - $textBegin, 2);
            $endUnit = intdiv($end - $textBegin, 2);
            if ($property['specialType'] === 2) {
                $objects[$start] = 2;
            } elseif ($property['specialType'] === 0) {
                $fontRuns[] = ['startUnit' => $startUnit, 'endUnit' => $endUnit, 'font' => $property['font']];
            } else {
                throw new RuntimeException('FDPC contains an unsupported special font type.');
            }
        }

        return ['objects' => $objects, 'fontRuns' => $fontRuns];
    }

    private function parseFdpp(string $contents, array $zone, array $textZone): array
    {
        $data = substr($contents, $zone['begin'], $zone['length']);
        $fod = $this->parseFodHeader($data, 'FDPP');
        $runs = [];
        $textBegin = (int) $textZone['begin'];
        $textEnd = $textBegin + (int) $textZone['length'];
        if ($fod['positions'][count($fod['positions']) - 1] !== $textEnd) {
            throw new RuntimeException('FDPP final text boundary does not match TEXT.');
        }
        for ($i = 0; $i < $fod['count']; ++$i) {
            $start = $fod['positions'][$i];
            $end = $fod['positions'][$i + 1];
            if ($start < $textBegin || $end < $start || $end > $textEnd || (($start - $textBegin) % 2) !== 0 || (($end - $textBegin) % 2) !== 0) {
                throw new RuntimeException('FDPP style boundary is outside aligned TEXT bytes.');
            }
            $propertyOffset = $fod['propertyOffsets'][$i];
            if ($propertyOffset === 0) {
                continue;
            }
            $paragraph = $this->parseParagraphProperty($data, $propertyOffset);
            $runs[] = [
                'startUnit' => intdiv($start - $textBegin, 2),
                'endUnit' => intdiv($end - $textBegin, 2),
                'paragraph' => $paragraph,
            ];
        }

        return $runs;
    }

    private function parseFodHeader(string $data, string $name): array
    {
        if (strlen($data) < 14) {
            throw new RuntimeException($name . ' zone is too short.');
        }
        $count = $this->u16($data, 0);
        if ($count < 1 || 8 + 6 * $count > strlen($data)) {
            throw new RuntimeException('Invalid ' . $name . ' FOD count.');
        }
        $positions = [];
        $offset = 4;
        for ($i = 0; $i <= $count; ++$i) {
            $positions[] = $this->u32($data, $offset);
            $offset += 4;
        }
        for ($i = 1; $i < count($positions); ++$i) {
            if ($positions[$i] < $positions[$i - 1]) {
                throw new RuntimeException($name . ' positions are not monotonic.');
            }
        }
        $propertyOffsets = [];
        for ($i = 0; $i < $count; ++$i) {
            $propertyOffsets[] = $this->u16($data, $offset);
            $offset += 2;
        }
        foreach ($propertyOffsets as $propertyOffset) {
            if ($propertyOffset !== 0 && ($propertyOffset < $offset || $propertyOffset >= strlen($data))) {
                throw new RuntimeException($name . ' property offset is outside the property region.');
            }
        }

        return ['count' => $count, 'positions' => $positions, 'propertyOffsets' => $propertyOffsets, 'propertyBegin' => $offset];
    }

    private function parseFontProperty(string $data, int $relativeOffset, array $fontNames): array
    {
        if ($relativeOffset + 4 > strlen($data)) {
            throw new RuntimeException('FDPC property offset points outside the zone.');
        }
        $size = $this->u16($data, $relativeOffset);
        if ($size < 4 || $relativeOffset + $size > strlen($data)) {
            throw new RuntimeException('Invalid FDPC property size.');
        }
        $pos = $relativeOffset + 4;
        $end = $relativeOffset + $size;
        $font = ['name' => 'Times New Roman', 'size' => 10, 'color' => '000000', 'bold' => false, 'italic' => false, 'underline' => 0];
        $specialType = 0;
        while ($pos < $end) {
            if ($pos + 2 > $end) {
                throw new RuntimeException('Truncated FDPC property tag.');
            }
            $tagPos = $pos;
            $tag = $this->u16($data, $pos);
            $pos += 2;
            $type = ($tag >> 8) & 0xFF;
            $id = $tag & 0xFF;
            if ($type === 0x0A || $type === 0x02) {
                $value = $type === 0x0A;
            } elseif ($type === 0x12 || $type === 0x18) {
                if ($pos + 2 > $end) {
                    throw new RuntimeException('Truncated FDPC 16-bit property.');
                }
                $value = $type === 0x12 ? ord($data[$pos]) : $this->u16($data, $pos);
                $pos += 2;
            } elseif ($type === 0x22) {
                if ($pos + 4 > $end) {
                    throw new RuntimeException('Truncated FDPC 32-bit property.');
                }
                $value = $this->u32($data, $pos);
                $pos += 4;
            } elseif ($type === 0x8A) {
                if ($pos + 2 > $end) {
                    throw new RuntimeException('Truncated FDPC array size.');
                }
                $extraSize = $this->u16($data, $pos);
                $arrayEnd = $tagPos + 2 + $extraSize;
                $pos += 2;
                if (($extraSize % 2) !== 0 || $arrayEnd > $end || $pos + 6 > $arrayEnd) {
                    throw new RuntimeException('Invalid FDPC font selector array.');
                }
                $pos += 2; // nested main value
                $childTag = $this->u16($data, $pos);
                $pos += 2;
                if ((($childTag >> 8) & 0xFF) !== 0x18 || ($childTag & 0xFF) !== 0) {
                    throw new RuntimeException('Unexpected FDPC font selector child.');
                }
                $fontId = $this->u16($data, $pos);
                $pos += 2;
                if ($fontId >= count($fontNames)) {
                    throw new RuntimeException('FDPC references a FONT id outside the table.');
                }
                $font['name'] = $fontNames[$fontId];
                if ($pos !== $arrayEnd) {
                    throw new RuntimeException('Unexpected extra data in FDPC font selector.');
                }

                continue;
            } else {
                throw new RuntimeException('Unsupported FDPC property type in emitted style subset.');
            }

            if ($id === 0 && $type === 0x12) {
                $specialType = (int) $value;
            } elseif ($id === 0x02 && ($type === 0x0A || $type === 0x02)) {
                $font['bold'] = (bool) $value;
            } elseif ($id === 0x03 && ($type === 0x0A || $type === 0x02)) {
                $font['italic'] = (bool) $value;
            } elseif ($id === 0x0C && $type === 0x22) {
                if ($value % 12700 !== 0) {
                    throw new RuntimeException('FDPC font size is not an exact integer point size.');
                }
                $font['size'] = intdiv($value, 12700);
            } elseif ($id === 0x1E && $type === 0x12) {
                $font['underline'] = (int) $value;
            } elseif ($id === 0x2E && $type === 0x22) {
                $font['color'] = sprintf('%02X%02X%02X', $value & 0xFF, ($value >> 8) & 0xFF, ($value >> 16) & 0xFF);
            } else {
                throw new RuntimeException('Unexpected FDPC character property in emitted subset.');
            }
        }
        if ($pos !== $end) {
            throw new RuntimeException('FDPC property did not terminate exactly.');
        }

        return ['specialType' => $specialType, 'font' => $font];
    }

    private function parseParagraphProperty(string $data, int $relativeOffset): array
    {
        if ($relativeOffset + 8 > strlen($data)) {
            throw new RuntimeException('FDPP property offset points outside the zone.');
        }
        $size = $this->u16($data, $relativeOffset);
        if ($size !== 8 || $relativeOffset + $size > strlen($data)) {
            throw new RuntimeException('Unexpected FDPP property size.');
        }
        if ($this->u16($data, $relativeOffset + 2) !== 0) {
            throw new RuntimeException('Unexpected FDPP main property value.');
        }
        $tag = $this->u16($data, $relativeOffset + 4);
        if ((($tag >> 8) & 0xFF) !== 0x12 || ($tag & 0xFF) !== 0x04) {
            throw new RuntimeException('Unexpected FDPP paragraph property tag.');
        }
        $alignment = ord($data[$relativeOffset + 6]);
        if ($alignment > 3) {
            throw new RuntimeException('Unsupported FDPP paragraph alignment.');
        }

        return ['alignment' => $alignment];
    }

    private function parseEobj(string $contents, array $zone): array
    {
        $data = substr($contents, $zone['begin'], $zone['length']);
        if (strlen($data) < 20) {
            throw new RuntimeException('EOBJ zone is too short.');
        }
        $count = $this->u32($data, 0);
        $dataSize = $this->u32($data, 4);
        if ($count < 1 || $count > 100000 || $dataSize !== 0) {
            throw new RuntimeException('Invalid EOBJ PLC header.');
        }
        $offset = 12;
        if ($offset + 4 * ($count + 1) > strlen($data)) {
            throw new RuntimeException('Truncated EOBJ position table.');
        }
        $pointers = [];
        for ($i = 0; $i <= $count; ++$i) {
            $pointers[] = $this->u32($data, $offset);
            $offset += 4;
        }

        $records = [];
        for ($i = 0; $i < $count; ++$i) {
            $record = $this->parseStructuredRecord($data, $offset, [0x1A, 0x22]);
            $offset = $record['end'];
            $v = $record['values'];
            $records[] = [
                'textUnitOffset' => (int) $pointers[$i],
                'type' => isset($v[0]) ? (int) $v[0] : -1,
                'widthEmu' => isset($v[1]) ? (int) $v[1] : -1,
                'heightEmu' => isset($v[2]) ? (int) $v[2] : -1,
                'objectId' => isset($v[3]) ? (int) $v[3] : -1,
            ];
        }
        if ($offset !== strlen($data)) {
            throw new RuntimeException('Unexpected trailing bytes in EOBJ zone.');
        }

        return $records;
    }

    private function parseFram(string $contents, array $zone): array
    {
        $data = substr($contents, $zone['begin'], $zone['length']);
        if (strlen($data) < 2) {
            throw new RuntimeException('FRAM zone is too short.');
        }
        $count = $this->u16($data, 0);
        $offset = 2;
        $frames = [];
        for ($i = 0; $i < $count; ++$i) {
            if ($offset + 4 > strlen($data)) {
                throw new RuntimeException('Truncated FRAM record.');
            }
            $size = $this->u16($data, $offset);
            $end = $offset + $size;
            if ($size < 4 || $end > strlen($data)) {
                throw new RuntimeException('Invalid FRAM record size.');
            }
            $pos = $offset + 4; // size + main value
            $frame = ['frameType' => -1, 'objectId' => -1, 'strsId' => -1, 'tableId' => -1];
            while ($pos < $end) {
                $tagStart = $pos;
                $tag = $this->u16($data, $pos);
                $pos += 2;
                $type = ($tag >> 8) & 0xFF;
                $id = $tag & 0xFF;
                if ($type === 0x12) {
                    if ($pos + 2 > $end) {
                        throw new RuntimeException('Truncated FRAM 0x12 property.');
                    }
                    $value = ord($data[$pos]);
                    $pos += 2;
                    if ($id === 1) {
                        $frame['frameType'] = $value;
                    }
                } elseif ($type === 0x22) {
                    if ($pos + 4 > $end) {
                        throw new RuntimeException('Truncated FRAM 0x22 property.');
                    }
                    $value = $this->u32($data, $pos);
                    $pos += 4;
                    if ($id === 0x18) {
                        $frame['strsId'] = (int) $value;
                    } elseif ($id === 0x2A) {
                        $frame['tableId'] = (int) $value;
                    }
                } elseif ($type === 0x82 && $id === 0x11) {
                    if ($pos + 2 > $end) {
                        throw new RuntimeException('Truncated FRAM object-id array.');
                    }
                    $extraSize = $this->u16($data, $pos);
                    $arrayEnd = $tagStart + 2 + $extraSize;
                    if ($extraSize !== 16 || $arrayEnd > $end || $pos + 16 > $end) {
                        throw new RuntimeException('Invalid FRAM object-id array.');
                    }
                    $pos += 2;
                    $main = $this->u16($data, $pos);
                    $pos += 2;
                    $a = $this->u32($data, $pos);
                    $pos += 4;
                    $b = $this->u32($data, $pos);
                    $pos += 4;
                    $c = $this->u32($data, $pos);
                    $pos += 4;
                    if ($main !== 0 || $b !== 0 || $c !== 0 || $pos !== $arrayEnd) {
                        throw new RuntimeException('Unexpected FRAM object-id array content.');
                    }
                    $frame['objectId'] = (int) $a;
                } else {
                    throw new RuntimeException('Unsupported FRAM field in emitted subset.');
                }
            }
            if ($pos !== $end) {
                throw new RuntimeException('FRAM record did not end on its declared boundary.');
            }
            $frames[] = $frame;
            $offset = $end;
        }
        if ($offset !== strlen($data)) {
            throw new RuntimeException('Unexpected trailing bytes in FRAM zone.');
        }

        return $frames;
    }

    private function parseMcld(string $contents, array $zone): array
    {
        $data = substr($contents, $zone['begin'], $zone['length']);
        if (strlen($data) < 12) {
            throw new RuntimeException('MCLD zone is too short.');
        }
        $maxUnknown = $this->u32($data, 0);
        $count = $this->u32($data, 4);
        if ($maxUnknown !== 0 || $count < 1 || $count > 1000 || 8 + 4 * $count > strlen($data)) {
            throw new RuntimeException('Invalid MCLD header.');
        }
        $offset = 8;
        $ids = [];
        for ($i = 0; $i < $count; ++$i) {
            $ids[] = $this->u32($data, $offset);
            $offset += 4;
        }

        $tables = [];
        for ($i = 0; $i < $count; ++$i) {
            $tableRecord = $this->parseStructuredRecord($data, $offset, [0x02, 0x22]);
            $offset = $tableRecord['end'];
            if ($offset + 4 > strlen($data)) {
                throw new RuntimeException('Truncated MCLD cell count.');
            }
            $cellCount = $this->u32($data, $offset);
            $offset += 4;
            if ($cellCount < 1 || $cellCount > 100) {
                throw new RuntimeException('MCLD table has an invalid cell count.');
            }
            $cells = [];
            for ($cell = 0; $cell < $cellCount; ++$cell) {
                $record = $this->parseStructuredRecord($data, $offset, [0x22]);
                $offset = $record['end'];
                $v = $record['values'];
                foreach (range(0, 5) as $required) {
                    if (!isset($v[$required])) {
                        throw new RuntimeException('MCLD cell misses geometry field ' . $required . '.');
                    }
                }
                $cells[] = [
                    'topEmu' => (int) $v[0],
                    'leftEmu' => (int) $v[1],
                    'bottomEmu' => (int) $v[2],
                    'rightEmu' => (int) $v[3],
                    'widthEmu' => (int) $v[4],
                    'heightEmu' => (int) $v[5],
                ];
            }
            $tables[] = ['tableId' => (int) $ids[$i], 'cells' => $cells];
        }
        if ($offset !== strlen($data)) {
            throw new RuntimeException('Unexpected trailing bytes in MCLD zone.');
        }

        return $tables;
    }

    private function parseTcd(string $contents, array $zone): array
    {
        $data = substr($contents, $zone['begin'], $zone['length']);
        if (strlen($data) < 20) {
            throw new RuntimeException('TCD zone is too short.');
        }
        $count = $this->u32($data, 0);
        $dataSize = $this->u32($data, 4);
        if ($count < 1 || $count > 100 || $dataSize !== 0 || 12 + 4 * ($count + 1) !== strlen($data)) {
            throw new RuntimeException('Invalid TCD PLC header or length.');
        }
        $offset = 12;
        $ends = [];
        for ($i = 0; $i < $count; ++$i) {
            $ends[] = $this->u32($data, $offset);
            $offset += 4;
        }
        $sentinel = $this->u32($data, $offset);
        if ($sentinel !== $ends[$count - 1]) {
            throw new RuntimeException('TCD final sentinel does not repeat the final cell end.');
        }
        for ($i = 1; $i < count($ends); ++$i) {
            if ($ends[$i] <= $ends[$i - 1]) {
                throw new RuntimeException('TCD cell boundaries are not strictly increasing.');
            }
        }

        return array_map('intval', $ends);
    }

    private function decodeTableCells(string $textBytes, array $zone, array $ends, array &$errors, int $tableId): array
    {
        $zoneBegin = (int) $zone['beginUnit'];
        $zoneEnd = (int) $zone['endUnit'];
        $zoneUnits = $zoneEnd - $zoneBegin;
        if ($ends === [] || end($ends) !== $zoneUnits) {
            $errors[] = 'TCD final boundary does not equal the STRS text-zone length for table ' . $tableId . '.';
        }

        $texts = [];
        $start = 0;
        foreach ($ends as $i => $end) {
            if ($end < $start || $end > $zoneUnits) {
                $errors[] = 'TCD cell range is outside STRS zone for table ' . $tableId . ', cell ' . $i . '.';
                $texts[] = null;

                continue;
            }
            $slice = substr($textBytes, 2 * ($zoneBegin + $start), 2 * ($end - $start));
            $decoded = Utf16::decodeLe($slice);
            $texts[] = $decoded === "\x01" ? '' : $decoded;

            if ($i + 1 < count($ends)) {
                if ($end >= $zoneUnits) {
                    $errors[] = 'Missing cell separator in table ' . $tableId . ', cell ' . $i . '.';
                    $start = $end;
                } else {
                    $separator = substr($textBytes, 2 * ($zoneBegin + $end), 2);
                    if (Utf16::decodeLe($separator) !== "\r") {
                        $errors[] = 'Cell separator is not CR in table ' . $tableId . ', after cell ' . $i . '.';
                    }
                    $start = $end + 1;
                }
            }
        }

        return $texts;
    }

    private function parseStructuredRecord(string $data, int $offset, array $allowedTypes): array
    {
        if ($offset + 4 > strlen($data)) {
            throw new RuntimeException('Truncated Works structured record.');
        }
        $size = $this->u16($data, $offset);
        $end = $offset + $size;
        if ($size < 4 || $end > strlen($data)) {
            throw new RuntimeException('Invalid Works structured record size.');
        }
        $pos = $offset + 2;
        $mainValue = $this->u16($data, $pos);
        $pos += 2;
        if ($mainValue !== 0) {
            throw new RuntimeException('Unexpected nonzero main value in emitted structured record.');
        }
        $values = [];
        while ($pos < $end) {
            if ($pos + 2 > $end) {
                throw new RuntimeException('Truncated Works property tag.');
            }
            $tag = $this->u16($data, $pos);
            $pos += 2;
            $type = ($tag >> 8) & 0xFF;
            $id = $tag & 0xFF;
            if (!in_array($type, $allowedTypes, true)) {
                throw new RuntimeException('Unexpected property type 0x' . dechex($type) . ' in emitted structured record.');
            }
            if ($type === 0x02) {
                $value = 0;
            } elseif ($type === 0x1A || $type === 0x12) {
                if ($pos + 2 > $end) {
                    throw new RuntimeException('Truncated 16-bit Works property.');
                }
                $value = $type === 0x12 ? ord($data[$pos]) : $this->u16($data, $pos);
                $pos += 2;
            } elseif ($type === 0x22) {
                if ($pos + 4 > $end) {
                    throw new RuntimeException('Truncated 32-bit Works property.');
                }
                $value = $this->u32($data, $pos);
                $pos += 4;
            } else {
                throw new RuntimeException('Unsupported structured property in validator subset.');
            }
            $values[$id] = $value;
        }
        if ($pos !== $end) {
            throw new RuntimeException('Structured record did not end at declared boundary.');
        }

        return ['end' => $end, 'values' => $values];
    }

    private function readObjectPayload(string $file, array $cfb, int $objectId): string
    {
        $storage = $this->findEntryByNameAndType($cfb['directory'], 'Object ' . $objectId, 1);
        if ($storage === null) {
            throw new RuntimeException('CFB storage for image object ' . $objectId . ' was not found.');
        }

        $childEntries = $this->collectSiblingTree($cfb['directory'], $storage['child']);
        $oleEntry = null;
        foreach ($childEntries as $entry) {
            if ($entry['type'] === 2 && strncmp($entry['name'], 'Ole10Native', 11) === 0) {
                $oleEntry = $entry;

                break;
            }
        }
        if ($oleEntry === null) {
            throw new RuntimeException('Ole10Native stream for image object ' . $objectId . ' was not found.');
        }
        if ($oleEntry['size'] < 4096) {
            throw new RuntimeException('Image Ole10Native stream unexpectedly uses Mini Stream storage.');
        }

        $ole = $this->readChain($file, $cfb['fat'], $oleEntry['start'], $oleEntry['size']);
        if (strlen($ole) < 4) {
            throw new RuntimeException('Ole10Native stream is too short.');
        }
        $payloadSize = $this->u32($ole, 0);
        if ($payloadSize < 1 || 4 + $payloadSize > strlen($ole)) {
            throw new RuntimeException('Ole10Native payload size is invalid.');
        }

        return substr($ole, 4, $payloadSize);
    }

    private function firstZone(array $zoneLists, string $name): ?array
    {
        return $zoneLists[$name][0] ?? null;
    }

    private function findZoneById(array $zoneLists, string $name, int $id): ?array
    {
        if (!isset($zoneLists[$name])) {
            return null;
        }
        $found = null;
        foreach ($zoneLists[$name] as $zone) {
            if ((int) $zone['id'] !== (int) $id) {
                continue;
            }
            if ($found !== null) {
                throw new RuntimeException('Duplicate ' . $name . ' zone id ' . $id . '.');
            }
            $found = $zone;
        }

        return $found;
    }

    private function collectSiblingTree(array $directory, int $index, array &$seen = []): array
    {
        if ($index === self::NOSTREAM) {
            return [];
        }
        if (!isset($directory[$index])) {
            throw new RuntimeException('CFB directory tree points outside the directory table.');
        }
        if (isset($seen[$index])) {
            throw new RuntimeException('Cyclic CFB directory sibling tree.');
        }
        $seen[$index] = true;
        $entry = $directory[$index];

        return array_merge(
            $this->collectSiblingTree($directory, $entry['left'], $seen),
            [$entry],
            $this->collectSiblingTree($directory, $entry['right'], $seen)
        );
    }

    private function findEntryByNameAndType(array $directory, string $name, int $type): ?array
    {
        foreach ($directory as $entry) {
            if ($entry['type'] === $type && $entry['name'] === $name) {
                return $entry;
            }
        }

        return null;
    }

    private function readChain(string $file, array $fat, int $start, ?int $size): string
    {
        if ($start === self::ENDOFCHAIN && ($size === null || $size === 0)) {
            return '';
        }

        $out = '';
        $sector = $start;
        $seen = [];
        while ($sector !== self::ENDOFCHAIN) {
            if ($sector === self::FREESECT || $sector === self::FATSECT || isset($seen[$sector])) {
                throw new RuntimeException('Invalid or cyclic CFB sector chain.');
            }
            if (!isset($fat[$sector])) {
                throw new RuntimeException('CFB sector is outside FAT.');
            }
            $seen[$sector] = true;
            $out .= $this->sector($file, $sector);
            if ($size !== null && strlen($out) >= $size) {
                return substr($out, 0, $size);
            }
            $sector = $fat[$sector];
        }

        if ($size !== null && strlen($out) < $size) {
            throw new RuntimeException('CFB stream chain ended before its declared size.');
        }

        return $size === null ? $out : substr($out, 0, $size);
    }

    private function sector(string $file, int $sector): string
    {
        $offset = 512 + $sector * 512;
        if ($offset < 512 || $offset + 512 > strlen($file)) {
            throw new RuntimeException('CFB sector points outside file.');
        }

        return substr($file, $offset, 512);
    }

    private function u16(string $data, int $offset): int
    {
        if ($offset < 0 || $offset + 2 > strlen($data)) {
            throw new RuntimeException('Unexpected end while reading uint16.');
        }

        $value = unpack('v', substr($data, $offset, 2));
        if ($value === false) {
            throw new RuntimeException('Unable to unpack uint16.');
        }

        return $value[1];
    }

    private function u32(string $data, int $offset): int
    {
        if ($offset < 0 || $offset + 4 > strlen($data)) {
            throw new RuntimeException('Unexpected end while reading uint32.');
        }

        $value = unpack('V', substr($data, $offset, 4));
        if ($value === false) {
            throw new RuntimeException('Unable to unpack uint32.');
        }

        return $value[1];
    }

    private function u64(string $data, int $offset): int
    {
        $low = $this->u32($data, $offset);
        $high = $this->u32($data, $offset + 4);

        return (int) ($low + $high * 4294967296);
    }
}
