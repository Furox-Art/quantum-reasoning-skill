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

final class Utf16
{
    public static function encodeLe(string $text): string
    {
        $text = (string) $text;
        $out = '';
        $len = strlen($text);
        for ($i = 0; $i < $len;) {
            $b0 = ord($text[$i]);
            if ($b0 < 0x80) {
                $cp = $b0;
                ++$i;
            } elseif (($b0 & 0xE0) === 0xC0 && $i + 1 < $len) {
                $cp = (($b0 & 0x1F) << 6) | (ord($text[$i + 1]) & 0x3F);
                $i += 2;
            } elseif (($b0 & 0xF0) === 0xE0 && $i + 2 < $len) {
                $cp = (($b0 & 0x0F) << 12) | ((ord($text[$i + 1]) & 0x3F) << 6) | (ord($text[$i + 2]) & 0x3F);
                $i += 3;
            } elseif (($b0 & 0xF8) === 0xF0 && $i + 3 < $len) {
                $cp = (($b0 & 0x07) << 18) | ((ord($text[$i + 1]) & 0x3F) << 12)
                    | ((ord($text[$i + 2]) & 0x3F) << 6) | (ord($text[$i + 3]) & 0x3F);
                $i += 4;
            } else {
                $cp = 0xFFFD;
                ++$i;
            }

            if ($cp <= 0xFFFF) {
                if ($cp >= 0xD800 && $cp <= 0xDFFF) {
                    $cp = 0xFFFD;
                }
                $out .= pack('v', $cp);
            } elseif ($cp <= 0x10FFFF) {
                $cp -= 0x10000;
                $out .= pack('v', 0xD800 | ($cp >> 10));
                $out .= pack('v', 0xDC00 | ($cp & 0x3FF));
            } else {
                $out .= pack('v', 0xFFFD);
            }
        }

        return $out;
    }

    public static function decodeLe(string $bytes): string
    {
        $out = '';
        $len = strlen($bytes) - (strlen($bytes) % 2);
        for ($i = 0; $i < $len; $i += 2) {
            $decoded = unpack('v', substr($bytes, $i, 2));
            if ($decoded === false) {
                throw new RuntimeException('Unable to decode UTF-16 code unit.');
            }
            $u = $decoded[1];
            if ($u >= 0xD800 && $u <= 0xDBFF && $i + 3 < $len) {
                $decoded2 = unpack('v', substr($bytes, $i + 2, 2));
                if ($decoded2 === false) {
                    throw new RuntimeException('Unable to decode UTF-16 surrogate code unit.');
                }
                $u2 = $decoded2[1];
                if ($u2 >= 0xDC00 && $u2 <= 0xDFFF) {
                    $cp = 0x10000 + (($u - 0xD800) << 10) + ($u2 - 0xDC00);
                    $i += 2;
                    $out .= self::codePointToUtf8($cp);

                    continue;
                }
            }
            $out .= self::codePointToUtf8($u);
        }

        return $out;
    }

    private static function codePointToUtf8(int $cp): string
    {
        if ($cp <= 0x7F) {
            return chr($cp);
        }
        if ($cp <= 0x7FF) {
            return chr(0xC0 | ($cp >> 6)) . chr(0x80 | ($cp & 0x3F));
        }
        if ($cp <= 0xFFFF) {
            return chr(0xE0 | ($cp >> 12)) . chr(0x80 | (($cp >> 6) & 0x3F)) . chr(0x80 | ($cp & 0x3F));
        }

        return chr(0xF0 | ($cp >> 18)) . chr(0x80 | (($cp >> 12) & 0x3F))
            . chr(0x80 | (($cp >> 6) & 0x3F)) . chr(0x80 | ($cp & 0x3F));
    }
}
