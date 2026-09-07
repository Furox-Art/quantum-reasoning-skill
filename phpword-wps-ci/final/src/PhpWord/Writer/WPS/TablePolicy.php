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

use PhpOffice\PhpWord\Element\Cell;
use PhpOffice\PhpWord\Element\Table;
use PhpOffice\PhpWord\Element\Text;
use PhpOffice\PhpWord\Element\TextBreak;
use PhpOffice\PhpWord\Element\TextRun;
use PhpOffice\PhpWord\Style\Table as TableStyle;

/**
 * Strict preflight/projection for the basic Works 7/8 table subset.
 *
 * The emitted subset is deliberately narrow and deterministic:
 * - rectangular tables, at most 100 cells (libwps' Works 7/8 limit),
 * - explicit per-column widths in twips,
 * - explicit exact row heights in twips,
 * - no merges, borders, shading, custom cell padding/positioning or row flags,
 * - text-only cell content (unsupported child elements become visible markers).
 *
 * Unsupported table layout is not approximated. The caller replaces the whole
 * table with a visible placeholder, matching the writer's unsupported-content
 * policy instead of silently changing geometry.
 */
final class TablePolicy
{
    private const EMU_PER_TWIP = 635;
    private const EMPTY_CELL_FILLER = "\x01";

    /** @var StylePolicy */
    private $stylePolicy;

    public function inspect(Table $table, string $path, CompatibilityReport $report): array
    {
        $facts = [
            'supported' => true,
            'path' => (string) $path,
            'rows' => 0,
            'columns' => 0,
            'widthEmu' => 0,
            'heightEmu' => 0,
            'columnWidthsEmu' => [],
            'rowHeightsEmu' => [],
            'cells' => [],
            'zoneText' => '',
            'zoneUnits' => 0,
            'cellEndUnitOffsets' => [],
            'fontRuns' => [],
            'paragraphRuns' => [],
        ];

        $this->stylePolicy = new StylePolicy();

        $rows = $table->getRows();
        $rowCount = count($rows);
        if ($rowCount < 1) {
            $this->fail($facts, $report, 'table_empty', 'Works table output requires at least one row.', $path);

            return $facts;
        }

        $columnCount = count($rows[0]->getCells());
        if ($columnCount < 1) {
            $this->fail($facts, $report, 'table_empty_row', 'Works table output requires at least one cell in every row.', $path);

            return $facts;
        }
        if ($rowCount * $columnCount > 100) {
            $this->fail($facts, $report, 'table_cell_limit', 'The Works 7/8 table parser accepts at most 100 cells in one MCLD table.', $path);
        }

        $this->inspectTableStyle($table, $path, $facts, $report);

        $columnWidths = [];
        $rowHeights = [];
        $cellContents = [];

        foreach ($rows as $rowIndex => $row) {
            $cells = $row->getCells();
            if (count($cells) !== $columnCount) {
                $this->fail(
                    $facts,
                    $report,
                    'table_non_rectangular',
                    'Rows with different cell counts cannot be mapped exactly by the current Works table subset.',
                    $path . '.row[' . $rowIndex . ']'
                );

                continue;
            }

            $rowStyle = $row->getStyle();
            $height = $row->getHeight();
            if (!is_numeric($height) || (float) $height <= 0.0 || !$rowStyle || !method_exists($rowStyle, 'isExactHeight') || !$rowStyle->isExactHeight()) {
                $this->fail(
                    $facts,
                    $report,
                    'table_row_height_not_exact',
                    'Each supported Works table row must have a positive explicit height with exactHeight=true; auto/minimum height is not approximated.',
                    $path . '.row[' . $rowIndex . ']'
                );
                $rowHeights[$rowIndex] = null;
            } else {
                $rowHeights[$rowIndex] = $this->twipToExactEmu($height, 'row height', $path . '.row[' . $rowIndex . ']', $facts, $report);
            }

            if ($rowStyle) {
                if (method_exists($rowStyle, 'isTblHeader') && $rowStyle->isTblHeader()) {
                    $this->fail($facts, $report, 'table_repeating_header_unsupported', 'Repeating table-header rows are not encoded in the current Works subset.', $path . '.row[' . $rowIndex . ']');
                }
                if (method_exists($rowStyle, 'isCantSplit') && $rowStyle->isCantSplit()) {
                    $this->fail($facts, $report, 'table_cant_split_unsupported', 'The row cantSplit rule is not encoded in the current Works subset.', $path . '.row[' . $rowIndex . ']');
                }
            }

            foreach ($cells as $columnIndex => $cell) {
                $cellPath = $path . '.row[' . $rowIndex . '].cell[' . $columnIndex . ']';
                $width = $cell->getWidth();
                if (!is_numeric($width) || (float) $width <= 0.0) {
                    $this->fail(
                        $facts,
                        $report,
                        'table_cell_width_missing',
                        'Each supported Works table column must have an explicit positive cell width in twips.',
                        $cellPath
                    );
                    $widthEmu = null;
                } else {
                    $widthEmu = $this->twipToExactEmu($width, 'cell width', $cellPath, $facts, $report);
                }

                if ($rowIndex === 0) {
                    $columnWidths[$columnIndex] = $widthEmu;
                } elseif ($widthEmu !== null && isset($columnWidths[$columnIndex]) && $columnWidths[$columnIndex] !== $widthEmu) {
                    $this->fail(
                        $facts,
                        $report,
                        'table_column_width_inconsistent',
                        'Cell widths differ within the same column; the current rectangular Works subset will not approximate them.',
                        $cellPath
                    );
                }

                $this->inspectCellStyle($cell, $cellPath, $facts, $report);
                $cellContents[$rowIndex][$columnIndex] = $this->extractCellText($cell, $cellPath, $report);
            }
        }

        if (!$facts['supported']) {
            return $facts;
        }

        $facts['rows'] = $rowCount;
        $facts['columns'] = $columnCount;
        $facts['columnWidthsEmu'] = array_values($columnWidths);
        $facts['rowHeightsEmu'] = array_values($rowHeights);
        $facts['widthEmu'] = array_sum($facts['columnWidthsEmu']);
        $facts['heightEmu'] = array_sum($facts['rowHeightsEmu']);

        if ($facts['widthEmu'] <= 0 || $facts['heightEmu'] <= 0 || $facts['widthEmu'] > 2147483647 || $facts['heightEmu'] > 2147483647) {
            $this->fail($facts, $report, 'table_dimensions_out_of_range', 'The complete table dimensions are outside the positive 32-bit EMU range used by Works 7/8.', $path);

            return $facts;
        }

        $zoneText = '';
        $zoneUnits = 0;
        $cellEnds = [];
        $cellsOut = [];
        $top = 0;
        $flatIndex = 0;
        $totalCells = $rowCount * $columnCount;

        for ($rowIndex = 0; $rowIndex < $rowCount; ++$rowIndex) {
            $left = 0;
            $heightEmu = $facts['rowHeightsEmu'][$rowIndex];
            for ($columnIndex = 0; $columnIndex < $columnCount; ++$columnIndex, ++$flatIndex) {
                $widthEmu = $facts['columnWidthsEmu'][$columnIndex];
                $cellContent = $cellContents[$rowIndex][$columnIndex];
                $logicalText = $cellContent['text'];
                $encodedText = $logicalText === '' ? self::EMPTY_CELL_FILLER : $logicalText;
                $encodedText = $this->normalizeText($encodedText);
                $units = $this->utf16Units($encodedText);

                $cellStartUnit = $zoneUnits;
                foreach ($cellContent['fontRuns'] as $run) {
                    $run['startUnit'] += $cellStartUnit;
                    $run['endUnit'] += $cellStartUnit;
                    $facts['fontRuns'][] = $run;
                }
                foreach ($cellContent['paragraphRuns'] as $run) {
                    $run['startUnit'] += $cellStartUnit;
                    $run['endUnit'] += $cellStartUnit;
                    $facts['paragraphRuns'][] = $run;
                }

                $zoneText .= $encodedText;
                $zoneUnits += $units;
                $cellEnds[] = $zoneUnits;

                $cellsOut[] = [
                    'index' => $flatIndex,
                    'row' => $rowIndex,
                    'column' => $columnIndex,
                    'text' => $logicalText,
                    'encodedText' => $encodedText,
                    'widthEmu' => $widthEmu,
                    'heightEmu' => $heightEmu,
                    'topEmu' => $top,
                    'leftEmu' => $left,
                    'bottomEmu' => $top + $heightEmu,
                    'rightEmu' => $left + $widthEmu,
                    'endUnitOffset' => $zoneUnits,
                ];

                if ($flatIndex + 1 < $totalCells) {
                    $zoneText .= "\r";
                    ++$zoneUnits;
                }
                $left += $widthEmu;
            }
            $top += $heightEmu;
        }

        $facts['cells'] = $cellsOut;
        $facts['zoneText'] = $zoneText;
        $facts['zoneUnits'] = $zoneUnits;
        $facts['cellEndUnitOffsets'] = $cellEnds;

        return $facts;
    }

    private function inspectTableStyle(Table $table, string $path, array &$facts, CompatibilityReport $report): void
    {
        $style = $table->getStyle();
        if (is_string($style)) {
            $this->fail($facts, $report, 'table_named_style_unresolved', 'Named table styles are not expanded by the current Works preflight, so their exact properties cannot be proven.', $path);

            return;
        }
        if (!$style) {
            return;
        }

        if (method_exists($style, 'getLayout') && $style->getLayout() !== TableStyle::LAYOUT_FIXED) {
            $this->fail($facts, $report, 'table_autofit_unsupported', 'AutoFit table geometry is dynamic; exact Works geometry requires layout=fixed.', $path);
        }
        if (method_exists($style, 'getAlignment')) {
            $alignment = $style->getAlignment();
            if ($alignment !== null && $alignment !== '') {
                $this->fail($facts, $report, 'table_alignment_unsupported', 'Explicit table alignment is not encoded in the current Works subset.', $path);
            }
        }
        if (method_exists($style, 'getCellSpacing') && $style->getCellSpacing() !== null && (float) $style->getCellSpacing() !== 0.0) {
            $this->fail($facts, $report, 'table_cell_spacing_unsupported', 'Explicit table cell spacing is not encoded in the current Works subset.', $path);
        }
        if (method_exists($style, 'getPosition') && $style->getPosition() !== null) {
            $this->fail($facts, $report, 'table_position_unsupported', 'Floating/positioned tables are not encoded by the current inline Works table path.', $path);
        }
        if (method_exists($style, 'getIndent') && $style->getIndent() !== null) {
            $this->fail($facts, $report, 'table_indent_unsupported', 'Table indentation is not encoded in the current Works subset.', $path);
        }
        if (method_exists($style, 'getBidiVisual') && $style->getBidiVisual() !== null) {
            $this->fail($facts, $report, 'table_bidi_unsupported', 'Bi-directional visual table ordering is not encoded in the current Works subset.', $path);
        }
        if (method_exists($style, 'getFirstRow') && $style->getFirstRow() !== null) {
            $this->fail($facts, $report, 'table_first_row_style_unsupported', 'A separate first-row table style is not encoded in the current Works subset.', $path);
        }
        if (method_exists($style, 'getShading') && $style->getShading() !== null) {
            $this->fail($facts, $report, 'table_shading_unsupported', 'Table shading is not encoded in the current Works subset.', $path);
        }
        if (method_exists($style, 'getBorderSize')) {
            foreach ((array) $style->getBorderSize() as $size) {
                if ($size !== null && (float) $size !== 0.0) {
                    $this->fail($facts, $report, 'table_border_unsupported', 'Table borders are not approximated by the current Works subset.', $path);

                    break;
                }
            }
        }

        foreach (['getCellMarginTop', 'getCellMarginLeft', 'getCellMarginRight', 'getCellMarginBottom'] as $method) {
            if (method_exists($style, $method)) {
                $value = $style->$method();
                if ($value !== null && (float) $value !== 0.0) {
                    $this->fail($facts, $report, 'table_cell_margin_unsupported', 'Explicit table cell margins are not encoded in the current Works subset.', $path);

                    break;
                }
            }
        }
    }

    private function inspectCellStyle(Cell $cell, string $path, array &$facts, CompatibilityReport $report): void
    {
        $style = $cell->getStyle();
        if (!$style) {
            return;
        }

        if (method_exists($style, 'getGridSpan')) {
            $span = $style->getGridSpan();
            if ($span !== null && (int) $span !== 1) {
                $this->fail($facts, $report, 'table_colspan_unsupported', 'Merged columns are not encoded by the current basic Works table subset.', $path);
            }
        }
        if (method_exists($style, 'getVMerge') && $style->getVMerge() !== null) {
            $this->fail($facts, $report, 'table_rowspan_unsupported', 'Merged rows are not encoded by the current basic Works table subset.', $path);
        }
        if (method_exists($style, 'getTextDirection') && $style->getTextDirection() !== null) {
            $this->fail($facts, $report, 'table_text_direction_unsupported', 'Custom table-cell text direction is not encoded in the current Works subset.', $path);
        }
        if (method_exists($style, 'getVAlign')) {
            $vAlign = $style->getVAlign();
            if ($vAlign !== null && $vAlign !== 'top') {
                $this->fail($facts, $report, 'table_vertical_alignment_unsupported', 'Only default/top cell vertical alignment is supported without approximation.', $path);
            }
        }
        if (method_exists($style, 'getShading') && $style->getShading() !== null) {
            $this->fail($facts, $report, 'table_cell_shading_unsupported', 'Cell shading is not encoded in the current Works subset.', $path);
        }
        if (method_exists($style, 'hasBorder') && $style->hasBorder()) {
            $this->fail($facts, $report, 'table_cell_border_unsupported', 'Cell borders are not approximated by the current Works subset.', $path);
        }

        foreach (['getPaddingTop', 'getPaddingLeft', 'getPaddingRight', 'getPaddingBottom'] as $method) {
            if (method_exists($style, $method)) {
                $value = $style->$method();
                if ($value !== null && (float) $value !== 0.0) {
                    $this->fail($facts, $report, 'table_cell_padding_unsupported', 'Explicit cell padding is not encoded in the current Works subset.', $path);

                    break;
                }
            }
        }
    }

    private function extractCellText(Cell $cell, string $path, CompatibilityReport $report): array
    {
        $text = '';
        $units = 0;
        $fontRuns = [];
        $paragraphRuns = [];
        $elements = $cell->getElements();
        $count = count($elements);

        foreach ($elements as $index => $element) {
            $childPath = $path . '.element[' . $index . ']';
            $paragraphStart = $units;
            $paragraphText = '';
            $paragraphFontRuns = [];
            $paragraphStyle = null;

            if ($element instanceof Text) {
                $paragraphText = $this->normalizeText((string) $element->getText());
                $len = $this->utf16Units($paragraphText);
                if ($len > 0) {
                    $paragraphFontRuns[] = [
                        'startUnit' => 0,
                        'endUnit' => $len,
                        'font' => $this->stylePolicy->inspectFont($element->getFontStyle(), $childPath . '.font', $report),
                    ];
                }
                $paragraphStyle = $element->getParagraphStyle();
            } elseif ($element instanceof TextRun) {
                $run = $this->extractTextRun($element, $childPath, $report);
                $paragraphText = $run['text'];
                $paragraphFontRuns = $run['fontRuns'];
                $paragraphStyle = $element->getParagraphStyle();
            } elseif ($element instanceof TextBreak) {
                $paragraphText = '';
            } else {
                $class = is_object($element) ? get_class($element) : gettype($element);
                $short = substr($class, strrpos($class, '\\') + 1);
                $report->addIssue(
                    'table_cell_element_unsupported',
                    'The table cell contains ' . $short . '; it is represented by an explicit placeholder inside the otherwise supported table.',
                    $childPath,
                    'error'
                );
                $paragraphText = '[PHPWord WPS: unsupported ' . $short . ' at ' . $childPath . ']';
            }

            $text .= $paragraphText;
            foreach ($paragraphFontRuns as $run) {
                $run['startUnit'] += $units;
                $run['endUnit'] += $units;
                $fontRuns[] = $run;
            }
            $units += $this->utf16Units($paragraphText);

            // Separate cell child blocks exactly as the previous table subset
            // did. The paragraph property covers the terminating CR so the
            // next paragraph can start with a new FDPP property.
            if ($index + 1 < $count) {
                $text .= "\r";
                ++$units;
            }
            if ($paragraphStyle !== null) {
                $paragraph = $this->stylePolicy->inspectParagraph($paragraphStyle, $childPath . '.paragraph', $report);
                if ((int) $paragraph['alignment'] !== 0 && $units > $paragraphStart) {
                    $paragraphRuns[] = [
                        'startUnit' => $paragraphStart,
                        'endUnit' => $units,
                        'paragraph' => $paragraph,
                    ];
                }
            }
        }

        return [
            'text' => $text,
            'fontRuns' => $this->mergeRuns($fontRuns, 'font'),
            'paragraphRuns' => $this->mergeRuns($paragraphRuns, 'paragraph'),
        ];
    }

    private function extractTextRun(TextRun $run, string $path, CompatibilityReport $report): array
    {
        $out = '';
        $units = 0;
        $fontRuns = [];
        foreach ($run->getElements() as $index => $element) {
            $childPath = $path . '.child[' . $index . ']';
            if ($element instanceof Text) {
                $part = $this->normalizeText((string) $element->getText());
                $len = $this->utf16Units($part);
                if ($len > 0) {
                    $fontRuns[] = [
                        'startUnit' => $units,
                        'endUnit' => $units + $len,
                        'font' => $this->stylePolicy->inspectFont($element->getFontStyle(), $childPath . '.font', $report),
                    ];
                }
                $out .= $part;
                $units += $len;
            } elseif ($element instanceof TextBreak) {
                $out .= "\r";
                ++$units;
            } else {
                $class = is_object($element) ? get_class($element) : gettype($element);
                $short = substr($class, strrpos($class, '\\') + 1);
                $report->addIssue(
                    'table_cell_inline_element_unsupported',
                    'The table cell text run contains ' . $short . '; it is represented by an explicit placeholder.',
                    $childPath,
                    'error'
                );
                $part = '[PHPWord WPS: unsupported ' . $short . ' at ' . $childPath . ']';
                $out .= $part;
                $units += $this->utf16Units($part);
            }
        }

        return ['text' => $out, 'fontRuns' => $this->mergeRuns($fontRuns, 'font')];
    }

    private function mergeRuns(array $runs, string $key): array
    {
        $out = [];
        foreach ($runs as $run) {
            $last = count($out) - 1;
            if ($last >= 0
                && $out[$last]['endUnit'] === $run['startUnit']
                && $out[$last][$key] === $run[$key]) {
                $out[$last]['endUnit'] = $run['endUnit'];
            } else {
                $out[] = $run;
            }
        }

        return $out;
    }

    /**
     * @param mixed $value
     */
    private function twipToExactEmu($value, string $what, string $path, array &$facts, CompatibilityReport $report): ?int
    {
        $raw = (float) $value * self::EMU_PER_TWIP;
        $rounded = round($raw);
        if (abs($raw - $rounded) > 1.0E-7 || $rounded <= 0 || $rounded > 2147483647) {
            $this->fail(
                $facts,
                $report,
                'table_dimension_not_exactly_representable',
                ucfirst($what) . ' cannot be represented exactly in the positive 32-bit EMU field used by Works 7/8.',
                $path
            );

            return null;
        }

        return (int) $rounded;
    }

    private function utf16Units(string $text): int
    {
        return intdiv(strlen(Utf16::encodeLe($text)), 2);
    }

    private function normalizeText(string $text): string
    {
        $text = str_replace(["\r\n", "\n"], "\r", (string) $text);

        return str_replace("\0", '', $text);
    }

    private function fail(array &$facts, CompatibilityReport $report, string $code, string $message, string $path): void
    {
        $facts['supported'] = false;
        $report->addIssue($code, $message, $path, 'error');
    }
}
