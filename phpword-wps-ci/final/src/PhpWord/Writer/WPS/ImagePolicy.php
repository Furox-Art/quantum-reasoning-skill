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

use PhpOffice\PhpWord\Element\Image;
use PhpOffice\PhpWord\Style\Frame;
use PhpOffice\PhpWord\Style\Image as ImageStyle;

/**
 * Strict image fidelity preflight for the Works 7/8 writer.
 *
 * Supported subset: byte-stable local/archive images with exact inline
 * placement and point dimensions that are exactly representable in EMUs.
 * The original image bytes are embedded unchanged in Ole10Native.
 */
final class ImagePolicy
{
    private const EMU_PER_POINT = 12700;

    public function inspect(Image $image, string $path, CompatibilityReport $report): array
    {
        $style = $image->getStyle();
        $sourceType = (string) $image->getSourceType();
        $mime = (string) $image->getImageType();
        $binary = $image->getImageString();

        $facts = [
            'supported' => true,
            'path' => (string) $path,
            'sourceType' => $sourceType,
            'mime' => $mime,
            'binary' => $binary,
            'sha256' => $binary === null ? null : hash('sha256', $binary),
            'byteLength' => $binary === null ? null : strlen($binary),
            'width' => $style === null ? null : $style->getWidth(),
            'height' => $style === null ? null : $style->getHeight(),
            'unit' => $style === null ? null : $style->getUnit(),
            'widthEmu' => null,
            'heightEmu' => null,
        ];

        if ($binary === null || $binary === '') {
            $this->fail($facts, $report, 'image_source_unreadable', 'The source image bytes could not be read; exact preservation cannot be verified.', $path);

            return $facts;
        }

        // Local and archive images expose stable source bytes. SOURCE_STRING is
        // ambiguous in PHPWord because HTTPS images are resolved into memory and
        // the original link is discarded; under strict fidelity it must fail.
        if ($sourceType !== Image::SOURCE_LOCAL && $sourceType !== Image::SOURCE_ARCHIVE) {
            $this->fail(
                $facts,
                $report,
                'image_source_semantics_unverifiable',
                'The image source is generated or resolved in memory, so original link/source semantics cannot be proven and preserved exactly.',
                $path
            );
        }

        if ($style === null) {
            $this->fail($facts, $report, 'image_style_missing', 'Image placement and physical size are unavailable.', $path);

            return $facts;
        }

        if (!$this->isStrictInlinePlacement($style)) {
            $this->fail(
                $facts,
                $report,
                'image_placement_unrepresentable',
                'Only exact inline/as-character placement is currently implemented for Works 7/8 images; no automatic repositioning is allowed.',
                $path
            );
        }

        if ($style->getUnit() !== Frame::UNIT_PT) {
            $this->fail(
                $facts,
                $report,
                'image_unit_unrepresentable',
                'The image size is not expressed in points, so an exact physical-size mapping cannot be proven without a conversion assumption.',
                $path
            );
        } else {
            $facts['widthEmu'] = $this->pointToExactEmu($style->getWidth(), 'width', $path, $facts, $report);
            $facts['heightEmu'] = $this->pointToExactEmu($style->getHeight(), 'height', $path, $facts, $report);
        }

        return $facts;
    }

    /**
     * @param mixed $value
     */
    private function pointToExactEmu($value, string $dimension, string $path, array &$facts, CompatibilityReport $report): ?int
    {
        if (!is_numeric($value) || (float) $value <= 0.0) {
            $this->fail($facts, $report, 'image_' . $dimension . '_missing', 'Image ' . $dimension . ' must be a positive physical size.', $path);

            return null;
        }

        $raw = (float) $value * self::EMU_PER_POINT;
        $rounded = round($raw);
        if (abs($raw - $rounded) > 1.0E-7 || $rounded > 2147483647) {
            $this->fail(
                $facts,
                $report,
                'image_' . $dimension . '_not_exactly_representable',
                'Image ' . $dimension . ' cannot be represented exactly in the integer EMU field used by Works 7/8.',
                $path
            );

            return null;
        }

        return (int) $rounded;
    }

    private function isStrictInlinePlacement(ImageStyle $style): bool
    {
        $wrap = $style->getWrap();
        $alignment = $style->getAlignment();
        $position = $style->getPosition();

        $wrapDistances = [
            $style->getWrapDistanceTop(),
            $style->getWrapDistanceBottom(),
            $style->getWrapDistanceLeft(),
            $style->getWrapDistanceRight(),
        ];
        foreach ($wrapDistances as $distance) {
            if ($distance !== null && (float) $distance !== 0.0) {
                return false;
            }
        }

        return ($wrap === null || $wrap === Frame::WRAP_INLINE)
            && ((float) $style->getLeft() === 0.0)
            && ((float) $style->getTop() === 0.0)
            && ($alignment === null || $alignment === '')
            && ($position === null || (float) $position === 0.0)
            && ($style->getPos() === null)
            && ($style->getHPos() === null || $style->getHPos() === Frame::POS_LEFT)
            && ($style->getHPosRelTo() === null || $style->getHPosRelTo() === Frame::POS_RELTO_CHAR)
            && ($style->getVPos() === null || $style->getVPos() === Frame::POS_TOP)
            && ($style->getVPosRelTo() === null || $style->getVPosRelTo() === Frame::POS_RELTO_LINE);
    }

    private function fail(array &$facts, CompatibilityReport $report, string $code, string $message, string $path): void
    {
        $facts['supported'] = false;
        $report->addIssue($code, $message, $path, 'fatal');
    }
}
