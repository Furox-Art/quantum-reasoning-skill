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
 * Compound File Binary (OLE/CFB v3) encoder for Microsoft Works 7/8 files.
 *
 * The writer deliberately avoids MiniFAT: every stream is represented with a
 * directory size of at least 4096 bytes and stored in normal 512-byte sectors.
 */
final class CompoundFile
{
    private const FREESECT = 0xFFFFFFFF;
    private const ENDOFCHAIN = 0xFFFFFFFE;
    private const FATSECT = 0xFFFFFFFD;
    private const NOSTREAM = 0xFFFFFFFF;
    private const SECTOR_SIZE = 512;
    private const MINI_STREAM_CUTOFF = 4096;

    /**
     * Encode a Works CFB file containing CONTENTS plus optional inline image OLE objects.
     *
     * @param string $contents Works CONTENTS stream
     * @param array  $images   Image projection records from DocumentText
     */
    public function encodeContents(string $contents, array $images = []): string
    {
        if (strlen($contents) < self::MINI_STREAM_CUTOFF) {
            throw new InvalidArgumentException('CONTENTS must be at least 4096 bytes to avoid MiniFAT storage.');
        }

        $streams = [
            [
                'key' => 'CONTENTS',
                'directoryName' => 'CONTENTS',
                'data' => (string) $contents,
            ],
        ];

        foreach ($images as $image) {
            if (!isset($image['objectId'], $image['binary'])) {
                throw new InvalidArgumentException('Image record is missing objectId or binary data.');
            }
            $objectId = (int) $image['objectId'];
            if ($objectId < 1) {
                throw new InvalidArgumentException('Image objectId must be positive.');
            }
            $payload = (string) $image['binary'];
            if ($payload === '') {
                throw new InvalidArgumentException('Image binary data must not be empty.');
            }

            // libwps readOle10Native() reads a 32-bit payload size followed by
            // those exact bytes. Padding is outside the payload and therefore
            // does not alter PNG/JPEG/GIF/BMP/TIFF metadata or compression.
            $ole = $this->u32(strlen($payload)) . $payload;
            if (strlen($ole) < self::MINI_STREAM_CUTOFF) {
                $ole = str_pad($ole, self::MINI_STREAM_CUTOFF, "\0");
            }

            $streams[] = [
                'key' => 'Object ' . $objectId . '/Ole10Native',
                'directoryName' => 'Ole10Native',
                'objectId' => $objectId,
                'data' => $ole,
            ];
        }

        return $this->encodeStreams($streams, $images);
    }

    private function encodeStreams(array $streams, array $images): string
    {
        $sectors = [];
        $streamMeta = [];

        foreach ($streams as $stream) {
            $data = (string) $stream['data'];
            if (strlen($data) < self::MINI_STREAM_CUTOFF) {
                throw new RuntimeException('Internal CFB stream unexpectedly fell below Mini Stream cutoff.');
            }
            $sectorCount = (int) ceil(strlen($data) / self::SECTOR_SIZE);
            $start = count($sectors);
            $padded = str_pad($data, $sectorCount * self::SECTOR_SIZE, "\0");
            for ($i = 0; $i < $sectorCount; ++$i) {
                $sectors[] = substr($padded, $i * self::SECTOR_SIZE, self::SECTOR_SIZE);
            }
            $streamMeta[$stream['key']] = [
                'start' => $start,
                'size' => strlen($data),
                'sectorCount' => $sectorCount,
            ];
        }

        $directoryEntries = $this->buildDirectoryEntries($streamMeta, $images);
        $directoryBytes = implode('', $directoryEntries);
        $directorySectorCount = (int) ceil(strlen($directoryBytes) / self::SECTOR_SIZE);
        $directoryBytes = str_pad($directoryBytes, $directorySectorCount * self::SECTOR_SIZE, "\0");
        $directoryStart = count($sectors);
        for ($i = 0; $i < $directorySectorCount; ++$i) {
            $sectors[] = substr($directoryBytes, $i * self::SECTOR_SIZE, self::SECTOR_SIZE);
        }

        $nonFatSectorCount = count($sectors);
        $fatSectorCount = 1;
        do {
            $old = $fatSectorCount;
            $fatSectorCount = (int) ceil(($nonFatSectorCount + $fatSectorCount) / 128);
        } while ($old !== $fatSectorCount);

        if ($fatSectorCount > 109) {
            throw new RuntimeException('WPS file is too large for the current no-DIFAT encoder.');
        }

        $firstFatSector = $nonFatSectorCount;
        $fatEntries = array_fill(0, $fatSectorCount * 128, self::FREESECT);

        foreach ($streamMeta as $meta) {
            $this->setChain($fatEntries, $meta['start'], $meta['sectorCount']);
        }
        $this->setChain($fatEntries, $directoryStart, $directorySectorCount);
        for ($i = 0; $i < $fatSectorCount; ++$i) {
            $fatEntries[$firstFatSector + $i] = self::FATSECT;
        }

        $fatBytes = '';
        foreach ($fatEntries as $entry) {
            $fatBytes .= $this->u32($entry);
        }
        for ($i = 0; $i < $fatSectorCount; ++$i) {
            $sectors[] = substr($fatBytes, $i * self::SECTOR_SIZE, self::SECTOR_SIZE);
        }

        return $this->header($fatSectorCount, $directoryStart, $firstFatSector) . implode('', $sectors);
    }

    /**
     * Directory layout:
     *   Root Entry
     *     child -> CONTENTS
     *   CONTENTS.right -> Object 1.right -> Object 2 ...
     *   Object N.child -> Ole10Native
     *
     * libwps groups OLE substreams by the numeric identifier in Object N.
     *
     * @return string[]
     */
    private function buildDirectoryEntries(array $streamMeta, array $images): array
    {
        usort($images, static function ($a, $b): int {
            return ((int) $a['objectId']) <=> ((int) $b['objectId']);
        });

        $entries = [];
        $contentsIndex = 1;
        $entries[] = $this->directoryEntry(
            'Root Entry',
            5,
            self::NOSTREAM,
            self::NOSTREAM,
            $contentsIndex,
            self::ENDOFCHAIN,
            0
        );

        $firstObjectIndex = $images === [] ? self::NOSTREAM : 2;
        $contentsMeta = $streamMeta['CONTENTS'];
        $entries[] = $this->directoryEntry(
            'CONTENTS',
            2,
            self::NOSTREAM,
            $firstObjectIndex,
            self::NOSTREAM,
            $contentsMeta['start'],
            $contentsMeta['size']
        );

        $imageCount = count($images);
        foreach ($images as $i => $image) {
            $objectId = (int) $image['objectId'];
            $storageIndex = 2 + 2 * $i;
            $streamIndex = $storageIndex + 1;
            $nextStorageIndex = ($i + 1 < $imageCount) ? $storageIndex + 2 : self::NOSTREAM;
            $key = 'Object ' . $objectId . '/Ole10Native';
            if (!isset($streamMeta[$key])) {
                throw new RuntimeException('Missing CFB image stream metadata for object ' . $objectId . '.');
            }

            $entries[] = $this->directoryEntry(
                'Object ' . $objectId,
                1,
                self::NOSTREAM,
                $nextStorageIndex,
                $streamIndex,
                self::ENDOFCHAIN,
                0
            );
            $meta = $streamMeta[$key];
            $entries[] = $this->directoryEntry(
                'Ole10Native',
                2,
                self::NOSTREAM,
                self::NOSTREAM,
                self::NOSTREAM,
                $meta['start'],
                $meta['size']
            );
        }

        return $entries;
    }

    private function setChain(array &$fatEntries, int $start, int $count): void
    {
        for ($i = 0; $i < $count; ++$i) {
            $fatEntries[$start + $i] = ($i === $count - 1) ? self::ENDOFCHAIN : $start + $i + 1;
        }
    }

    private function header(int $fatSectors, int $directorySector, int $firstFatSector): string
    {
        $h = "\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" . str_repeat("\0", 16);
        $h .= $this->u16(0x003E) . $this->u16(3) . $this->u16(0xFFFE);
        $h .= $this->u16(9) . $this->u16(6) . str_repeat("\0", 6);
        $h .= $this->u32(0); // directory sectors for CFB v3
        $h .= $this->u32($fatSectors);
        $h .= $this->u32($directorySector);
        $h .= $this->u32(0); // transaction signature
        $h .= $this->u32(self::MINI_STREAM_CUTOFF);
        $h .= $this->u32(self::ENDOFCHAIN) . $this->u32(0); // MiniFAT
        $h .= $this->u32(self::ENDOFCHAIN) . $this->u32(0); // DIFAT chain

        for ($i = 0; $i < 109; ++$i) {
            $h .= $this->u32($i < $fatSectors ? $firstFatSector + $i : self::FREESECT);
        }

        if (strlen($h) !== self::SECTOR_SIZE) {
            throw new RuntimeException('Internal CFB header size mismatch.');
        }

        return $h;
    }

    private function directoryEntry(string $name, int $type, int $left, int $right, int $child, int $startSector, int $size): string
    {
        $nameBytes = Utf16::encodeLe($name . "\0");
        if (strlen($nameBytes) > 64) {
            throw new InvalidArgumentException('CFB directory name is too long.');
        }

        $entry = str_pad($nameBytes, 64, "\0");
        $entry .= $this->u16(strlen($nameBytes));
        $entry .= chr($type) . chr(1); // black node
        $entry .= $this->u32($left) . $this->u32($right) . $this->u32($child);
        $entry .= str_repeat("\0", 16); // CLSID
        $entry .= $this->u32(0); // state bits
        $entry .= str_repeat("\0", 16); // creation + modified times
        $entry .= $this->u32($startSector) . $this->u64($size);

        if (strlen($entry) !== 128) {
            throw new RuntimeException('Internal CFB directory entry size mismatch.');
        }

        return $entry;
    }

    private function u16(int $value): string
    {
        return pack('v', $value & 0xFFFF);
    }

    private function u32(int $value): string
    {
        return pack('V', $value & 0xFFFFFFFF);
    }

    private function u64(int $value): string
    {
        $low = $value & 0xFFFFFFFF;
        $high = (int) floor($value / 4294967296);

        return $this->u32($low) . $this->u32($high);
    }
}
