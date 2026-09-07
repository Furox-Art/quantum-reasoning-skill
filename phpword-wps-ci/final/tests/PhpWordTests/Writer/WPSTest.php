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

namespace PhpOffice\PhpWordTests\Writer;

use PhpOffice\PhpWord\IOFactory;
use PhpOffice\PhpWord\PhpWord;
use PhpOffice\PhpWord\Settings;
use PhpOffice\PhpWord\SimpleType\Jc;
use PhpOffice\PhpWord\Style\Font;
use PhpOffice\PhpWord\Writer\WPS;
use PHPUnit\Framework\TestCase;
use RuntimeException;

class WPSTest extends TestCase
{
    public function testWritesRealWorksCompoundDocument(): void
    {
        $phpWord = new PhpWord();
        $section = $phpWord->addSection();
        $section->addText('Hello Works');
        $section->addText('Second paragraph');

        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($file);

        try {
            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');
            $writer->save($file);

            $bytes = file_get_contents($file);
            self::assertNotFalse($bytes);
            self::assertSame("\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", substr($bytes, 0, 8));

            $validation = $writer->getLastValidation();
            self::assertNotNull($validation);
            self::assertTrue($validation['valid'], implode('; ', $validation['errors']));
            self::assertSame("Hello Works\rSecond paragraph\r", $validation['text']);
            self::assertFalse($writer->getCompatibilityReport()->hasErrors());
        } finally {
            @unlink($file);
        }
    }

    public function testUnsupportedPageBreakIsVisibleAndReported(): void
    {
        $phpWord = new PhpWord();
        $section = $phpWord->addSection();
        $section->addText('Before');
        $section->addPageBreak();
        $section->addText('After');

        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($file);

        try {
            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');
            $writer->save($file);

            self::assertTrue($writer->getCompatibilityReport()->hasErrors());
            self::assertNotEmpty($writer->getCompatibilityReport()->getIssues());
            $validation = $writer->getLastValidation();
            self::assertTrue($validation['valid']);
            self::assertStringContainsString('unsupported PageBreak', $validation['text']);
        } finally {
            @unlink($file);
        }
    }

    public function testBasicCharacterAndParagraphStylesRoundTripInWorksBinary(): void
    {
        $phpWord = new PhpWord();
        $section = $phpWord->addSection();
        $section->addText('Normal');
        $section->addText('Bold', ['bold' => true, 'size' => 14]);
        $section->addText('Italic', ['italic' => true]);
        $section->addText('Under', ['underline' => Font::UNDERLINE_SINGLE]);
        $section->addText('Color', ['color' => 'E02030']);
        $section->addText('Center', null, ['alignment' => Jc::CENTER]);
        $section->addText('Courier', ['name' => 'Courier New', 'size' => 12]);

        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($file);

        try {
            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');
            $writer->save($file);

            $validation = $writer->getLastValidation();
            self::assertTrue($validation['valid'], implode('; ', $validation['errors']));
            self::assertSame("Normal\rBold\rItalic\rUnder\rColor\rCenter\rCourier\r", $validation['text']);
            self::assertSame([Settings::getDefaultFontName(), 'Courier New'], $validation['styles']['fontNames']);
            self::assertCount(7, $validation['styles']['fontRuns']);

            $fonts = array_column($validation['styles']['fontRuns'], 'font');
            self::assertSame(Settings::getDefaultFontName(), $fonts[0]['name']);
            self::assertSame((int) Settings::getDefaultFontSize(), $fonts[0]['size']);
            self::assertTrue($fonts[1]['bold']);
            self::assertSame(14, $fonts[1]['size']);
            self::assertTrue($fonts[2]['italic']);
            self::assertSame(1, $fonts[3]['underline']);
            self::assertSame('E02030', $fonts[4]['color']);
            self::assertSame('Courier New', $fonts[6]['name']);
            self::assertSame(12, $fonts[6]['size']);

            self::assertCount(1, $validation['styles']['paragraphRuns']);
            self::assertSame(2, $validation['styles']['paragraphRuns'][0]['paragraph']['alignment']);
        } finally {
            @unlink($file);
        }
    }

    public function testUnsupportedCharacterStyleFailsBeforeWriting(): void
    {
        $phpWord = new PhpWord();
        $section = $phpWord->addSection();
        $section->addText('No approximation', ['superScript' => true]);

        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($file);

        try {
            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');

            try {
                $writer->save($file);
                self::fail('Unsupported character style must abort the strict writer.');
            } catch (RuntimeException $e) {
                self::assertStringContainsString('font_superscript_unsupported', $e->getMessage());
            }

            self::assertTrue($writer->getCompatibilityReport()->hasFatalErrors());
            self::assertSame(0, filesize($file));
        } finally {
            @unlink($file);
        }
    }

    public function testImageIsEmbeddedByteForByteWithExactInlineObjectMetadata(): void
    {
        $png = tempnam(sys_get_temp_dir(), 'phpword-wps-img-');
        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($png);
        self::assertNotFalse($file);

        // 10x10 PNG containing a tEXt metadata chunk: Comment=preserve-me.
        $fixture = base64_decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAE3RFWHRDb21tZW50AHByZXNlcnZlLW1lDBPzAAAAABRJREFUeJxj+M/A8J8YzDCqkL4KAZLDxzmrOvyxAAAAAElFTkSuQmCC',
            true
        );
        self::assertNotFalse($fixture);
        file_put_contents($png, $fixture);

        try {
            $phpWord = new PhpWord();
            $section = $phpWord->addSection();
            $section->addText('Before');
            $section->addImage($png, ['width' => 20, 'height' => 20]);
            $section->addText('After');

            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');
            $writer->save($file);

            self::assertFalse($writer->getCompatibilityReport()->hasErrors());
            $validation = $writer->getLastValidation();
            self::assertTrue($validation['valid'], implode('; ', $validation['errors']));
            self::assertSame("Before\r\u{FFFC}\rAfter\r", $validation['text']);
            self::assertCount(1, $validation['images']);
            self::assertSame(1, $validation['images'][0]['objectId']);
            self::assertSame(7, $validation['images'][0]['textUnitOffset']);
            self::assertSame(254000, $validation['images'][0]['widthEmu']);
            self::assertSame(254000, $validation['images'][0]['heightEmu']);
            self::assertSame(strlen($fixture), $validation['images'][0]['byteLength']);
            self::assertSame(hash('sha256', $fixture), $validation['images'][0]['sha256']);
        } finally {
            @unlink($png);
            @unlink($file);
        }
    }

    public function testImagePlacementMismatchIsFatalBeforeWriting(): void
    {
        $png = tempnam(sys_get_temp_dir(), 'phpword-wps-img-');
        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($png);
        self::assertNotFalse($file);

        $fixture = base64_decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAE3RFWHRDb21tZW50AHByZXNlcnZlLW1lDBPzAAAAABRJREFUeJxj+M/A8J8YzDCqkL4KAZLDxzmrOvyxAAAAAElFTkSuQmCC',
            true
        );
        self::assertNotFalse($fixture);
        file_put_contents($png, $fixture);

        try {
            $phpWord = new PhpWord();
            $section = $phpWord->addSection();
            $section->addImage($png, ['width' => 20, 'height' => 20, 'marginLeft' => 1]);

            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');

            try {
                $writer->save($file);
                self::fail('Strict image placement mismatch must abort the writer.');
            } catch (RuntimeException $e) {
                self::assertStringContainsString('image_placement_unrepresentable', $e->getMessage());
            }

            self::assertTrue($writer->getCompatibilityReport()->hasFatalErrors());
            self::assertSame(0, filesize($file));
        } finally {
            @unlink($png);
            @unlink($file);
        }
    }

    public function testBasicFixedTableIsWrittenAsRealWorksTable(): void
    {
        $phpWord = new PhpWord();
        $section = $phpWord->addSection();
        $section->addText('Before');
        $table = $section->addTable(['layout' => 'fixed']);

        $row = $table->addRow(432, ['exactHeight' => true]); // 0.3 inch
        $row->addCell(1440)->addText('A'); // 1 inch
        $row->addCell(2880)->addText('B'); // 2 inches
        $row = $table->addRow(720, ['exactHeight' => true]); // 0.5 inch
        $row->addCell(1440)->addText('C');
        $row->addCell(2880)->addText('D');
        $section->addText('After');

        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($file);

        try {
            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');
            $writer->save($file);

            self::assertFalse($writer->getCompatibilityReport()->hasErrors());
            $validation = $writer->getLastValidation();
            self::assertTrue($validation['valid'], implode('; ', $validation['errors']));
            self::assertSame("Before\r\u{FFFC}After\r", $validation['text']);
            self::assertCount(1, $validation['tables']);

            $actual = $validation['tables'][0];
            self::assertSame(1, $actual['objectId']);
            self::assertSame(1, $actual['tableId']);
            self::assertSame(1, $actual['strsId']);
            self::assertSame(7, $actual['textUnitOffset']);
            self::assertSame(2743200, $actual['widthEmu']);
            self::assertSame(731520, $actual['heightEmu']);
            self::assertSame(2, $actual['rows']);
            self::assertSame(2, $actual['columns']);
            self::assertSame(['A', 'B', 'C', 'D'], array_column($actual['cells'], 'text'));

            self::assertSame(914400, $actual['cells'][0]['widthEmu']);
            self::assertSame(1828800, $actual['cells'][1]['widthEmu']);
            self::assertSame(274320, $actual['cells'][0]['heightEmu']);
            self::assertSame(457200, $actual['cells'][2]['heightEmu']);
        } finally {
            @unlink($file);
        }
    }

    public function testBasicStylesInsideRealWorksTableArePreserved(): void
    {
        $phpWord = new PhpWord();
        $section = $phpWord->addSection();
        $table = $section->addTable(['layout' => 'fixed']);

        $row = $table->addRow(432, ['exactHeight' => true]);
        $row->addCell(1440)->addText('A', ['bold' => true], ['alignment' => Jc::CENTER]);
        $row->addCell(2880)->addText('B', ['italic' => true]);
        $row = $table->addRow(720, ['exactHeight' => true]);
        $row->addCell(1440)->addText('C', ['color' => 'FF0000']);
        $row->addCell(2880)->addText('D', ['underline' => Font::UNDERLINE_SINGLE]);

        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($file);

        try {
            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');
            $writer->save($file);
            $validation = $writer->getLastValidation();

            self::assertTrue($validation['valid'], implode('; ', $validation['errors']));
            self::assertSame(['A', 'B', 'C', 'D'], array_column($validation['tables'][0]['cells'], 'text'));
            $fonts = array_column($validation['styles']['fontRuns'], 'font');
            self::assertTrue($fonts[0]['bold']);
            self::assertTrue($fonts[1]['italic']);
            self::assertSame('FF0000', $fonts[2]['color']);
            self::assertSame(1, $fonts[3]['underline']);
            self::assertSame(2, $validation['styles']['paragraphRuns'][0]['paragraph']['alignment']);
        } finally {
            @unlink($file);
        }
    }

    public function testEmptyTableCellRemainsLogicallyEmpty(): void
    {
        $phpWord = new PhpWord();
        $section = $phpWord->addSection();
        $table = $section->addTable(['layout' => 'fixed']);
        $row = $table->addRow(432, ['exactHeight' => true]);
        $row->addCell(1440);
        $row->addCell(1440)->addText('B');

        $file = tempnam(sys_get_temp_dir(), 'phpword-wps-');
        self::assertNotFalse($file);

        try {
            /** @var WPS $writer */
            $writer = IOFactory::createWriter($phpWord, 'WPS');
            $writer->save($file);
            $validation = $writer->getLastValidation();
            self::assertTrue($validation['valid'], implode('; ', $validation['errors']));
            self::assertSame('', $validation['tables'][0]['cells'][0]['text']);
            self::assertSame('B', $validation['tables'][0]['cells'][1]['text']);
        } finally {
            @unlink($file);
        }
    }
}
