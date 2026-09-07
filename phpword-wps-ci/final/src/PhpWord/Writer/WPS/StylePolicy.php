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

use PhpOffice\PhpWord\Settings;
use PhpOffice\PhpWord\Style;
use PhpOffice\PhpWord\Style\Font;
use PhpOffice\PhpWord\Style\Paragraph;

/**
 * Strict normalization of the basic style subset represented by Works 7/8.
 *
 * Supported character properties: font name, integer point size, RGB color,
 * bold, italic and the underline variants for which libwps exposes a stable
 * Works numeric mapping. Supported paragraph property: horizontal alignment.
 * Any explicitly requested style outside this subset is a fatal fidelity error.
 */
final class StylePolicy
{
    private const UNDERLINE_MAP = [
        Font::UNDERLINE_NONE => 0,
        Font::UNDERLINE_SINGLE => 1,
        Font::UNDERLINE_WORDS => 2,
        Font::UNDERLINE_DOUBLE => 3,
        Font::UNDERLINE_DOTTED => 4,
        Font::UNDERLINE_HEAVY => 6,
        Font::UNDERLINE_DASH => 7,
        Font::UNDERLINE_DOTDASH => 9,
        Font::UNDERLINE_DOTDOTDASH => 10,
        Font::UNDERLINE_WAVY => 11,
        Font::UNDERLINE_WAVYHEAVY => 16,
        Font::UNDERLINE_DOTTEDHEAVY => 17,
        Font::UNDERLINE_DASHHEAVY => 18,
        Font::UNDERLINE_DOTDASHHEAVY => 19,
        Font::UNDERLINE_DOTDOTDASHHEAVY => 20,
        Font::UNDERLINE_DASHLONG => 21,
        Font::UNDERLINE_DASHLONGHEAVY => 22,
        Font::UNDERLINE_WAVYDOUBLE => 23,
    ];

    /**
     * @param null|Font|string $style
     */
    public function inspectFont($style, string $path, CompatibilityReport $report): array
    {
        $font = $this->resolveStyle($style, Font::class, $path, 'font', $report);
        $facts = [
            'name' => Settings::getDefaultFontName(),
            'size' => (int) Settings::getDefaultFontSize(),
            'color' => strtoupper(Settings::getDefaultFontColor()),
            'bold' => false,
            'italic' => false,
            'underline' => 0,
        ];

        if (!$font instanceof Font) {
            return $facts;
        }

        $name = $font->getName();
        if ($name !== null && $name !== '') {
            if (!$this->isAsciiFontName($name)) {
                $this->fatal($report, 'font_name_unrepresentable', 'The Works FONT table subset only preserves printable ASCII font names exactly.', $path);
            } else {
                $facts['name'] = $name;
            }
        }

        $size = $font->getSize();
        if ($size !== null) {
            $number = (float) $size;
            if ($number <= 0 || $number > 1000 || abs($number - round($number)) > 1.0E-9) {
                $this->fatal($report, 'font_size_unrepresentable', 'Works/libwps basic font size is preserved exactly only for positive integer point sizes.', $path);
            } else {
                $facts['size'] = (int) round($number);
            }
        }

        $color = $font->getColor();
        if ($color !== null && $color !== '') {
            $color = strtoupper(ltrim((string) $color, '#'));
            if (!preg_match('/^[0-9A-F]{6}$/D', $color)) {
                $this->fatal($report, 'font_color_unrepresentable', 'Font color must be an exact six-digit RGB value for Works output.', $path);
            } else {
                $facts['color'] = $color;
            }
        }

        $facts['bold'] = (bool) $font->isBold();
        $facts['italic'] = (bool) $font->isItalic();
        $underline = $font->getUnderline();
        if (!array_key_exists($underline, self::UNDERLINE_MAP)) {
            $this->fatal($report, 'font_underline_unrepresentable', 'The requested underline style has no verified Works 7/8 mapping.', $path);
        } else {
            $facts['underline'] = self::UNDERLINE_MAP[$underline];
        }

        $this->rejectUnsupportedFontProperties($font, $path, $report);

        return $facts;
    }

    /**
     * @param null|Paragraph|string $style
     */
    public function inspectParagraph($style, string $path, CompatibilityReport $report): array
    {
        $paragraph = $this->resolveStyle($style, Paragraph::class, $path, 'paragraph', $report);
        $facts = ['alignment' => 0];
        if (!$paragraph instanceof Paragraph) {
            return $facts;
        }

        $alignment = $paragraph->getAlignment();
        $map = [
            '' => 0,
            'start' => 0,
            'left' => 0,
            'end' => 1,
            'right' => 1,
            'center' => 2,
            'both' => 3,
            'justify' => 3,
        ];
        if (!array_key_exists((string) $alignment, $map)) {
            $this->fatal($report, 'paragraph_alignment_unrepresentable', 'The requested paragraph alignment has no exact Works 7/8 mapping.', $path);
        } else {
            $facts['alignment'] = $map[(string) $alignment];
        }

        $this->rejectUnsupportedParagraphProperties($paragraph, $path, $report);

        return $facts;
    }

    /**
     * @param null|Font|Paragraph|string $style
     * @param class-string<Font|Paragraph> $class
     *
     * @return null|Font|Paragraph
     */
    private function resolveStyle($style, string $class, string $path, string $kind, CompatibilityReport $report)
    {
        if (is_string($style)) {
            $resolved = Style::getStyle($style);
            if (!$resolved instanceof $class) {
                $this->fatal($report, $kind . '_named_style_unresolved', 'Named ' . $kind . ' style "' . $style . '" cannot be resolved to the expected PHPWord style type.', $path);

                return null;
            }

            return $resolved;
        }
        if ($style === null) {
            return null;
        }
        if (!$style instanceof $class) {
            $this->fatal($report, $kind . '_style_type_unsupported', 'Unexpected PHPWord ' . $kind . ' style object cannot be preserved exactly.', $path);

            return null;
        }

        return $style;
    }

    private function rejectUnsupportedFontProperties(Font $font, string $path, CompatibilityReport $report): void
    {
        $checks = [
            ['getHint', null, 'font_hint_unsupported'],
            ['isSuperScript', false, 'font_superscript_unsupported'],
            ['isSubScript', false, 'font_subscript_unsupported'],
            ['isStrikethrough', false, 'font_strike_unsupported'],
            ['isDoubleStrikethrough', false, 'font_double_strike_unsupported'],
            ['isSmallCaps', false, 'font_small_caps_unsupported'],
            ['isAllCaps', false, 'font_all_caps_unsupported'],
            ['getFgColor', null, 'font_highlight_unsupported'],
            ['getScale', null, 'font_scale_unsupported'],
            ['getSpacing', null, 'font_spacing_unsupported'],
            ['getKerning', null, 'font_kerning_unsupported'],
            ['getShading', null, 'font_shading_unsupported'],
            ['getLang', null, 'font_language_unsupported'],
            ['isRTL', false, 'font_rtl_unsupported'],
            ['isHidden', false, 'font_hidden_unsupported'],
            ['getPosition', null, 'font_position_unsupported'],
            ['getWhiteSpace', '', 'font_whitespace_mode_unsupported'],
            ['getFallbackFont', '', 'font_fallback_unsupported'],
        ];
        foreach ($checks as [$method, $default, $code]) {
            if (!method_exists($font, $method)) {
                continue;
            }
            $value = $font->$method();
            if (!$this->equivalentDefault($value, $default)) {
                $this->fatal($report, $code, 'This character-style property is outside the verified basic Works subset and will not be approximated.', $path);
            }
        }
    }

    private function rejectUnsupportedParagraphProperties(Paragraph $paragraph, string $path, CompatibilityReport $report): void
    {
        if (!in_array($paragraph->getBasedOn(), [null, '', 'Normal'], true)) {
            $this->fatal($report, 'paragraph_inheritance_unsupported', 'Paragraph inheritance other than Normal is not flattened by the Works basic-style subset.', $path);
        }
        $checks = [
            ['getNext', null, 'paragraph_next_style_unsupported'],
            ['getIndentation', null, 'paragraph_indentation_unsupported'],
            ['getSpace', null, 'paragraph_spacing_unsupported'],
            ['getLineHeight', null, 'paragraph_line_height_unsupported'],
            ['isKeepNext', false, 'paragraph_keep_next_unsupported'],
            ['isKeepLines', false, 'paragraph_keep_lines_unsupported'],
            ['hasPageBreakBefore', false, 'paragraph_page_break_unsupported'],
            ['getNumStyle', null, 'paragraph_numbering_unsupported'],
            ['getTabs', [], 'paragraph_tabs_unsupported'],
            ['getShading', null, 'paragraph_shading_unsupported'],
            ['hasContextualSpacing', false, 'paragraph_contextual_spacing_unsupported'],
            ['isBidi', false, 'paragraph_bidi_unsupported'],
            ['getTextAlignment', null, 'paragraph_text_alignment_unsupported'],
            ['hasSuppressAutoHyphens', false, 'paragraph_hyphenation_unsupported'],
        ];
        foreach ($checks as [$method, $default, $code]) {
            if (!method_exists($paragraph, $method)) {
                continue;
            }
            $value = $paragraph->$method();
            if (!$this->equivalentDefault($value, $default)) {
                $this->fatal($report, $code, 'This paragraph-style property is outside the verified basic Works subset and will not be approximated.', $path);
            }
        }
        if (!$paragraph->hasWidowControl()) {
            $this->fatal($report, 'paragraph_widow_control_unsupported', 'Disabling widow control is outside the verified basic Works subset.', $path);
        }
        if ($paragraph->hasBorder()) {
            $this->fatal($report, 'paragraph_border_unsupported', 'Paragraph borders are outside the verified basic Works subset.', $path);
        }
    }

    /**
     * @param mixed $value
     * @param mixed $default
     */
    private function equivalentDefault($value, $default): bool
    {
        if (is_array($default)) {
            return (array) $value === $default;
        }
        if ($default === false) {
            return $value === false || $value === null;
        }

        return $value === $default;
    }

    private function isAsciiFontName(string $name): bool
    {
        return $name !== '' && strlen($name) <= 255 && preg_match('/^[\x20-\x7E]+$/D', $name) === 1;
    }

    private function fatal(CompatibilityReport $report, string $code, string $message, string $path): void
    {
        $report->addIssue($code, $message, $path, 'fatal');
    }
}
