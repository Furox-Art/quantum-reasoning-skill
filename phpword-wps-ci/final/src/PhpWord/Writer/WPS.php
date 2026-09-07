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

namespace PhpOffice\PhpWord\Writer;

use PhpOffice\PhpWord\PhpWord;
use PhpOffice\PhpWord\Writer\WPS\CompatibilityReport;
use PhpOffice\PhpWord\Writer\WPS\CompoundFile;
use PhpOffice\PhpWord\Writer\WPS\Contents;
use PhpOffice\PhpWord\Writer\WPS\DocumentText;
use PhpOffice\PhpWord\Writer\WPS\Validator;
use RuntimeException;

/**
 * Microsoft Works 7/8 WPS writer.
 */
class WPS extends AbstractWriter implements WriterInterface
{
    /** @var CompatibilityReport */
    private $compatibilityReport;

    /** @var null|array */
    private $lastValidation;

    public function __construct(?PhpWord $phpWord = null)
    {
        $this->setPhpWord($phpWord);
        $this->compatibilityReport = new CompatibilityReport();
    }

    public function save(string $filename): void
    {
        $this->compatibilityReport = new CompatibilityReport();
        $projection = (new DocumentText())->extract($this->getPhpWord(), $this->compatibilityReport);
        if ($this->compatibilityReport->hasFatalErrors()) {
            $fatal = [];
            foreach ($this->compatibilityReport->getIssues() as $issue) {
                if ($issue['severity'] === 'fatal') {
                    $fatal[] = $issue['code'] . ' at ' . $issue['path'] . ': ' . $issue['message'];
                }
            }

            throw new RuntimeException('WPS fidelity preflight failed: ' . implode('; ', $fatal));
        }

        $contents = (new Contents())->encode($projection['text'], $projection['images'], $projection['tables'], $projection['styles']);
        $file = (new CompoundFile())->encodeContents($contents, $projection['images']);

        $actualFilename = $this->getTempFile($filename);
        if (file_put_contents($actualFilename, $file) === false) {
            throw new RuntimeException("Could not write '{$actualFilename}'.");
        }

        $this->lastValidation = (new Validator())->validateFile($actualFilename, $projection);
        if (!$this->lastValidation['valid']) {
            @unlink($actualFilename);
            $this->clearTempDir();

            throw new RuntimeException('Independent WPS validation failed: ' . implode('; ', $this->lastValidation['errors']));
        }

        $this->cleanupTempFile();
    }

    public function getCompatibilityReport(): CompatibilityReport
    {
        return $this->compatibilityReport;
    }

    public function getLastValidation(): ?array
    {
        return $this->lastValidation;
    }
}
