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

class CompatibilityReport
{
    /** @var array */
    private $issues = [];

    public function addIssue(string $code, string $message, string $path, string $severity = 'error'): void
    {
        $this->issues[] = [
            'code' => (string) $code,
            'message' => (string) $message,
            'path' => (string) $path,
            'severity' => (string) $severity,
        ];
    }

    public function getIssues(): array
    {
        return $this->issues;
    }

    public function hasErrors(): bool
    {
        foreach ($this->issues as $issue) {
            if ($issue['severity'] === 'error' || $issue['severity'] === 'fatal') {
                return true;
            }
        }

        return false;
    }

    public function hasFatalErrors(): bool
    {
        foreach ($this->issues as $issue) {
            if ($issue['severity'] === 'fatal') {
                return true;
            }
        }

        return false;
    }
}
