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
use PhpOffice\PhpWord\Element\Table;
use PhpOffice\PhpWord\Element\Text;
use PhpOffice\PhpWord\Element\TextBreak;
use PhpOffice\PhpWord\Element\TextRun;
use PhpOffice\PhpWord\PhpWord;

/**
 * Conservative PhpWord -> Works document projection.
 *
 * Supported inline images/tables are represented by U+FFFC object markers.
 * Basic character and paragraph styles are captured as UTF-16 ranges and are
 * encoded independently by Contents. Fidelity failures classified as fatal
 * abort output before any destination file is produced.
 */
final class DocumentText
{
    /** @var array */
    private $images = [];

    /** @var array */
    private $tables = [];

    /** @var array */
    private $fontRuns = [];

    /** @var array */
    private $paragraphRuns = [];

    /** @var int */
    private $utf16Units = 0;

    /** @var int */
    private $nextObjectId = 1;

    /** @var StylePolicy */
    private $stylePolicy;

    public function extract(PhpWord $phpWord, CompatibilityReport $report): array
    {
        $this->images = [];
        $this->tables = [];
        $this->fontRuns = [];
        $this->paragraphRuns = [];
        $this->utf16Units = 0;
        $this->nextObjectId = 1;
        $this->stylePolicy = new StylePolicy();
        $out = '';

        foreach ($phpWord->getSections() as $sectionIndex => $section) {
            foreach ($section->getElements() as $elementIndex => $element) {
                $path = 'section[' . $sectionIndex . '].element[' . $elementIndex . ']';
                $out .= $this->renderBlock($element, $path, $report);
            }
        }

        return [
            'text' => $out,
            'images' => $this->images,
            'tables' => $this->tables,
            'styles' => [
                'fontRuns' => $this->mergeRuns($this->fontRuns, 'font'),
                'paragraphRuns' => $this->mergeRuns($this->paragraphRuns, 'paragraph'),
            ],
        ];
    }

    /**
     * @param mixed $element
     */
    private function renderBlock($element, string $path, CompatibilityReport $report): string
    {
        if ($element instanceof Text) {
            $paragraphStart = $this->utf16Units;
            $text = $this->appendStyledText((string) $element->getText(), $element->getFontStyle(), $path . '.font', $report);
            $text .= $this->append("\r");
            $this->addParagraphRun($paragraphStart, $this->utf16Units, $element->getParagraphStyle(), $path . '.paragraph', $report);

            return $text;
        }

        if ($element instanceof TextRun) {
            $paragraphStart = $this->utf16Units;
            $text = '';
            foreach ($element->getElements() as $index => $child) {
                $text .= $this->renderInline($child, $path . '.child[' . $index . ']', $report);
            }
            $text .= $this->append("\r");
            $this->addParagraphRun($paragraphStart, $this->utf16Units, $element->getParagraphStyle(), $path . '.paragraph', $report);

            return $text;
        }

        if ($element instanceof TextBreak) {
            return $this->append("\r");
        }

        if ($element instanceof Image) {
            $marker = $this->renderImage($element, $path, $report);

            return $marker . $this->append("\r");
        }

        if ($element instanceof Table) {
            // A Works inline table is itself the paragraph-level object. Adding
            // CR immediately after U+FFFC creates an observable blank paragraph
            // in libwps/LibreOffice, so the marker is emitted without one.
            return $this->renderTable($element, $path, $report);
        }

        return $this->unsupported($element, $path, $report);
    }

    /**
     * @param mixed $element
     */
    private function renderInline($element, string $path, CompatibilityReport $report): string
    {
        if ($element instanceof Text) {
            return $this->appendStyledText((string) $element->getText(), $element->getFontStyle(), $path . '.font', $report);
        }
        if ($element instanceof TextBreak) {
            return $this->append("\r");
        }
        if ($element instanceof Image) {
            return $this->renderImage($element, $path, $report);
        }
        if ($element instanceof Table) {
            return $this->unsupported($element, $path, $report, false);
        }

        return $this->unsupported($element, $path, $report, false);
    }

    /**
     * @param mixed $fontStyle
     */
    private function appendStyledText(string $text, $fontStyle, string $path, CompatibilityReport $report): string
    {
        $text = $this->normalizeText((string) $text);
        $start = $this->utf16Units;
        $out = $this->append($text);
        $end = $this->utf16Units;
        if ($end > $start) {
            $font = $this->stylePolicy->inspectFont($fontStyle, $path, $report);
            $this->fontRuns[] = ['startUnit' => $start, 'endUnit' => $end, 'font' => $font];
        }

        return $out;
    }

    /**
     * @param mixed $paragraphStyle
     */
    private function addParagraphRun(int $start, int $end, $paragraphStyle, string $path, CompatibilityReport $report): void
    {
        if ($end <= $start) {
            return;
        }
        $paragraph = $this->stylePolicy->inspectParagraph($paragraphStyle, $path, $report);
        if ((int) $paragraph['alignment'] !== 0) {
            $this->paragraphRuns[] = ['startUnit' => (int) $start, 'endUnit' => (int) $end, 'paragraph' => $paragraph];
        }
    }

    private function renderImage(Image $image, string $path, CompatibilityReport $report): string
    {
        $facts = (new ImagePolicy())->inspect($image, $path, $report);
        if (!$facts['supported']) {
            return $this->append('[PHPWord WPS: image fidelity failure at ' . $path . ']');
        }

        $facts['objectId'] = $this->nextObjectId++;
        $facts['textUnitOffset'] = $this->utf16Units;
        $this->images[] = $facts;

        return $this->append("\u{FFFC}");
    }

    private function renderTable(Table $table, string $path, CompatibilityReport $report): string
    {
        $facts = (new TablePolicy())->inspect($table, $path, $report);
        if (!$facts['supported']) {
            return $this->append('[PHPWord WPS: table fidelity failure at ' . $path . "]\r");
        }

        $facts['objectId'] = $this->nextObjectId++;
        $facts['tableId'] = count($this->tables) + 1;
        // STRS vector index 0 is the main document; each table gets one
        // following type-5 auxiliary text zone.
        $facts['strsId'] = count($this->tables) + 1;
        $facts['textUnitOffset'] = $this->utf16Units;
        $this->tables[] = $facts;

        return $this->append("\u{FFFC}");
    }

    private function append(string $text): string
    {
        $text = $this->normalizeText((string) $text);
        $this->utf16Units += intdiv(strlen(Utf16::encodeLe($text)), 2);

        return $text;
    }

    private function normalizeText(string $text): string
    {
        $text = str_replace(["\r\n", "\n"], "\r", (string) $text);

        return str_replace("\0", '', $text);
    }

    private function mergeRuns(array $runs, string $key): array
    {
        $out = [];
        foreach ($runs as $run) {
            if ($run['endUnit'] <= $run['startUnit']) {
                continue;
            }
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
     * @param mixed $element
     */
    private function unsupported($element, string $path, CompatibilityReport $report, bool $block = true): string
    {
        $class = is_object($element) ? get_class($element) : gettype($element);
        $short = substr($class, strrpos($class, '\\') + 1);
        $report->addIssue(
            'unsupported_element',
            'Microsoft Works WPS encoding is not implemented for ' . $short . '.',
            $path,
            'error'
        );
        $marker = '[PHPWord WPS: unsupported ' . $short . ' at ' . $path . ']';

        return $this->append($block ? $marker . "\r" : $marker);
    }
}
