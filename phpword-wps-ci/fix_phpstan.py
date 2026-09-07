from pathlib import Path
import sys
root=Path(sys.argv[1]) / 'src/PhpWord/Writer/WPS'

def rep(file, pairs):
    p=root/file
    s=p.read_text()
    for a,b in pairs:
        if a not in s:
            print('MISSING',file,a[:90])
        s=s.replace(a,b)
    p.write_text(s)

rep('CompatibilityReport.php',[
('public function addIssue($code, $message, $path, $severity = \'error\'): void', 'public function addIssue(string $code, string $message, string $path, string $severity = \'error\'): void'),
])
rep('CompoundFile.php',[
('public function encodeContents($contents, array $images = []): string','public function encodeContents(string $contents, array $images = []): string'),
('private function setChain(array &$fatEntries, $start, $count): void','private function setChain(array &$fatEntries, int $start, int $count): void'),
('private function header($fatSectors, $directorySector, $firstFatSector): string','private function header(int $fatSectors, int $directorySector, int $firstFatSector): string'),
('private function directoryEntry($name, $type, $left, $right, $child, $startSector, $size): string','private function directoryEntry(string $name, int $type, int $left, int $right, int $child, int $startSector, int $size): string'),
('private function u16($value): string','private function u16(int $value): string'),
('private function u32($value): string','private function u32(int $value): string'),
('private function u64($value): string','private function u64(int $value): string'),
])
rep('Contents.php',[
('public function encode($text, array $images = [], array $tables = [], array $styles = []): string','public function encode(string $text, array $images = [], array $tables = [], array $styles = []): string'),
('private function encodeFdpc(array $objects, array $fontRuns, array $fontIds, $textOffset, $mainTextEnd, $fullTextEnd): string','private function encodeFdpc(array $objects, array $fontRuns, array $fontIds, int $textOffset, int $mainTextEnd, int $fullTextEnd): string'),
('private function encodeFdpp(array $paragraphRuns, $textOffset, $fullTextEnd): string','private function encodeFdpp(array $paragraphRuns, int $textOffset, int $fullTextEnd): string'),
('private function fontProperty(array $font, $fontId): string','private function fontProperty(array $font, int $fontId): string'),
('private function fontArrayProperty($fontId): string','private function fontArrayProperty(int $fontId): string'),
('private function fontNameRecord($name): string','private function fontNameRecord(string $name): string'),
('private function rgbValue($hex): int','private function rgbValue(string $hex): int'),
('private function encodeStrs($mainUnits, array $tables): string','private function encodeStrs(int $mainUnits, array $tables): string'),
('private function record($main): string','private function record(int $main): string'),
('private function dataArray3($id, $a, $b, $c): string','private function dataArray3(int $id, int $a, int $b, int $c): string'),
('private function dataBoolTrue($id): string','private function dataBoolTrue(int $id): string'),
('private function normalizeRuns(array $runs, $key): array','private function normalizeRuns(array $runs, string $key): array'),
('private function data16($id, $type, $value): string','private function data16(int $id, int $type, int $value): string'),
('private function data32($id, $type, $value): string','private function data32(int $id, int $type, int $value): string'),
('private function indexRegionSize($zoneCount): int','private function indexRegionSize(int $zoneCount): int'),
('private function indexEntry($name, $type, $id, $offset, $length): string','private function indexEntry(string $name, string $type, int $id, int $offset, int $length): string'),
('private function normalizeText($text): string','private function normalizeText(string $text): string'),
('private function u16($value): string','private function u16(int $value): string'),
('private function i16($value): string','private function i16(int $value): string'),
('private function u32($value): string','private function u32(int $value): string'),
])
rep('DocumentText.php',[
('private function renderBlock($element, $path, CompatibilityReport $report): string', '/**\n     * @param mixed $element\n     */\n    private function renderBlock($element, string $path, CompatibilityReport $report): string'),
('private function renderInline($element, $path, CompatibilityReport $report): string', '/**\n     * @param mixed $element\n     */\n    private function renderInline($element, string $path, CompatibilityReport $report): string'),
('private function appendStyledText($text, $fontStyle, $path, CompatibilityReport $report): string', '/**\n     * @param mixed $fontStyle\n     */\n    private function appendStyledText(string $text, $fontStyle, string $path, CompatibilityReport $report): string'),
('private function addParagraphRun($start, $end, $paragraphStyle, $path, CompatibilityReport $report): void', '/**\n     * @param mixed $paragraphStyle\n     */\n    private function addParagraphRun(int $start, int $end, $paragraphStyle, string $path, CompatibilityReport $report): void'),
('private function renderImage(Image $image, $path, CompatibilityReport $report): string','private function renderImage(Image $image, string $path, CompatibilityReport $report): string'),
('private function renderTable(Table $table, $path, CompatibilityReport $report): string','private function renderTable(Table $table, string $path, CompatibilityReport $report): string'),
('private function append($text): string','private function append(string $text): string'),
('private function normalizeText($text): string','private function normalizeText(string $text): string'),
('private function mergeRuns(array $runs, $key): array','private function mergeRuns(array $runs, string $key): array'),
('private function unsupported($element, $path, CompatibilityReport $report, $block = true): string','/**\n     * @param mixed $element\n     */\n    private function unsupported($element, string $path, CompatibilityReport $report, bool $block = true): string'),
])
rep('ImagePolicy.php',[
('use PhpOffice\\PhpWord\\Style\\Frame;','use PhpOffice\\PhpWord\\Style\\Frame;\nuse PhpOffice\\PhpWord\\Style\\Image as ImageStyle;'),
('public function inspect(Image $image, $path, CompatibilityReport $report): array','public function inspect(Image $image, string $path, CompatibilityReport $report): array'),
('private function pointToExactEmu($value, $dimension, $path, array &$facts, CompatibilityReport $report)','/**\n     * @param mixed $value\n     */\n    private function pointToExactEmu($value, string $dimension, string $path, array &$facts, CompatibilityReport $report): ?int'),
('private function isStrictInlinePlacement($style): bool','private function isStrictInlinePlacement(ImageStyle $style): bool'),
("        $alignment = method_exists($style, 'getAlignment') ? $style->getAlignment() : '';\n        $position = method_exists($style, 'getPosition') ? $style->getPosition() : null;","        $alignment = $style->getAlignment();\n        $position = $style->getPosition();"),
('private function fail(array &$facts, CompatibilityReport $report, $code, $message, $path): void','private function fail(array &$facts, CompatibilityReport $report, string $code, string $message, string $path): void'),
])
rep('StylePolicy.php',[
('public function inspectFont($style, $path, CompatibilityReport $report): array','/**\n     * @param Font|string|null $style\n     */\n    public function inspectFont($style, string $path, CompatibilityReport $report): array'),
('public function inspectParagraph($style, $path, CompatibilityReport $report): array','/**\n     * @param Paragraph|string|null $style\n     */\n    public function inspectParagraph($style, string $path, CompatibilityReport $report): array'),
('private function resolveStyle($style, $class, $path, $kind, CompatibilityReport $report)','/**\n     * @param Font|Paragraph|string|null $style\n     * @param class-string<Font|Paragraph> $class\n     * @return Font|Paragraph|null\n     */\n    private function resolveStyle($style, string $class, string $path, string $kind, CompatibilityReport $report)'),
('private function rejectUnsupportedFontProperties(Font $font, $path, CompatibilityReport $report): void','private function rejectUnsupportedFontProperties(Font $font, string $path, CompatibilityReport $report): void'),
('private function rejectUnsupportedParagraphProperties(Paragraph $paragraph, $path, CompatibilityReport $report): void','private function rejectUnsupportedParagraphProperties(Paragraph $paragraph, string $path, CompatibilityReport $report): void'),
("        if (method_exists($paragraph, 'getBasedOn') && !in_array($paragraph->getBasedOn(), [null, '', 'Normal'], true)) {","        if (!in_array($paragraph->getBasedOn(), [null, '', 'Normal'], true)) {"),
("        if (method_exists($paragraph, 'hasWidowControl') && !$paragraph->hasWidowControl()) {","        if (!$paragraph->hasWidowControl()) {"),
("        if (method_exists($paragraph, 'hasBorder') && $paragraph->hasBorder()) {","        if ($paragraph->hasBorder()) {"),
('private function equivalentDefault($value, $default): bool','/**\n     * @param mixed $value\n     * @param mixed $default\n     */\n    private function equivalentDefault($value, $default): bool'),
('private function isAsciiFontName($name): bool','private function isAsciiFontName(string $name): bool'),
('private function fatal(CompatibilityReport $report, $code, $message, $path): void','private function fatal(CompatibilityReport $report, string $code, string $message, string $path): void'),
])
rep('TablePolicy.php',[
('public function inspect(Table $table, $path, CompatibilityReport $report): array','public function inspect(Table $table, string $path, CompatibilityReport $report): array'),
('private function inspectTableStyle(Table $table, $path, array &$facts, CompatibilityReport $report): void','private function inspectTableStyle(Table $table, string $path, array &$facts, CompatibilityReport $report): void'),
('private function inspectCellStyle(Cell $cell, $path, array &$facts, CompatibilityReport $report): void','private function inspectCellStyle(Cell $cell, string $path, array &$facts, CompatibilityReport $report): void'),
('private function extractCellText(Cell $cell, $path, CompatibilityReport $report): array','private function extractCellText(Cell $cell, string $path, CompatibilityReport $report): array'),
('private function extractTextRun(TextRun $run, $path, CompatibilityReport $report): array','private function extractTextRun(TextRun $run, string $path, CompatibilityReport $report): array'),
('private function mergeRuns(array $runs, $key): array','private function mergeRuns(array $runs, string $key): array'),
('private function twipToExactEmu($value, $what, $path, array &$facts, CompatibilityReport $report)','/**\n     * @param mixed $value\n     */\n    private function twipToExactEmu($value, string $what, string $path, array &$facts, CompatibilityReport $report): ?int'),
('private function utf16Units($text): int','private function utf16Units(string $text): int'),
('private function normalizeText($text): string','private function normalizeText(string $text): string'),
('private function fail(array &$facts, CompatibilityReport $report, $code, $message, $path): void','private function fail(array &$facts, CompatibilityReport $report, string $code, string $message, string $path): void'),
])
rep('Utf16.php',[
('public static function encodeLe($text): string','public static function encodeLe(string $text): string'),
('public static function decodeLe($bytes): string','public static function decodeLe(string $bytes): string'),
('private static function codePointToUtf8($cp): string','private static function codePointToUtf8(int $cp): string'),
("            $u = unpack('v', substr($bytes, $i, 2))[1];","            $decoded = unpack('v', substr($bytes, $i, 2));\n            if ($decoded === false) {\n                throw new \\RuntimeException('Unable to decode UTF-16 code unit.');\n            }\n            $u = $decoded[1];"),
("                $u2 = unpack('v', substr($bytes, $i + 2, 2))[1];","                $decoded2 = unpack('v', substr($bytes, $i + 2, 2));\n                if ($decoded2 === false) {\n                    throw new \\RuntimeException('Unable to decode UTF-16 surrogate code unit.');\n                }\n                $u2 = $decoded2[1];"),
])
rep('Validator.php',[
('private function failure($message): array','private function failure(string $message): array'),
('private function parseCfb($file): array','private function parseCfb(string $file): array'),
('private function parseContents($contents): array','private function parseContents(string $contents): array'),
('private function parseStrs($contents, array $zone, $totalTextUnits): array','private function parseStrs(string $contents, array $zone, int $totalTextUnits): array'),
('private function validateImages($file, array $cfb, array $works, array $expectedImages, array $fdpcObjects, array $eobjRecords, array &$errors): array','private function validateImages(string $file, array $cfb, array $works, array $expectedImages, array $fdpcObjects, array $eobjRecords, array &$errors): array'),
('private function validateTables($contents, array $works, array $expectedTables, array $fdpcObjects, array $eobjRecords, array &$errors): array','private function validateTables(string $contents, array $works, array $expectedTables, array $fdpcObjects, array $eobjRecords, array &$errors): array'),
('private function compareObjectRecord(array $actual, array $expected, $expectedType, $label, array &$errors): void','private function compareObjectRecord(array $actual, array $expected, int $expectedType, string $label, array &$errors): void'),
('private function parseFontTable($contents, ?array $zone): array','private function parseFontTable(string $contents, ?array $zone): array'),
('private function flattenExpectedStyles($mainText, array $tables, array $styles): array','private function flattenExpectedStyles(string $mainText, array $tables, array $styles): array'),
('private function normalizeExpectedRuns(array $runs, $key): array','private function normalizeExpectedRuns(array $runs, string $key): array'),
('private function compareStyleRuns(array $actual, array $expected, $kind, array &$errors): void','private function compareStyleRuns(array $actual, array $expected, string $kind, array &$errors): void'),
('private function parseFdpc($contents, array $zone, array $textZone, array $fontNames): array','private function parseFdpc(string $contents, array $zone, array $textZone, array $fontNames): array'),
('private function parseFdpp($contents, array $zone, array $textZone): array','private function parseFdpp(string $contents, array $zone, array $textZone): array'),
('private function parseFodHeader($data, $name): array','private function parseFodHeader(string $data, string $name): array'),
('private function parseFontProperty($data, $relativeOffset, array $fontNames): array','private function parseFontProperty(string $data, int $relativeOffset, array $fontNames): array'),
('private function parseParagraphProperty($data, $relativeOffset): array','private function parseParagraphProperty(string $data, int $relativeOffset): array'),
('        if ($alignment < 0 || $alignment > 3) {','        if ($alignment > 3) {'),
('private function parseEobj($contents, array $zone): array','private function parseEobj(string $contents, array $zone): array'),
('private function parseFram($contents, array $zone): array','private function parseFram(string $contents, array $zone): array'),
('private function parseMcld($contents, array $zone): array','private function parseMcld(string $contents, array $zone): array'),
('private function parseTcd($contents, array $zone): array','private function parseTcd(string $contents, array $zone): array'),
('private function decodeTableCells($textBytes, array $zone, array $ends, array &$errors, $tableId): array','private function decodeTableCells(string $textBytes, array $zone, array $ends, array &$errors, int $tableId): array'),
('private function parseStructuredRecord($data, $offset, array $allowedTypes): array','private function parseStructuredRecord(string $data, int $offset, array $allowedTypes): array'),
('private function readObjectPayload($file, array $cfb, $objectId): string','private function readObjectPayload(string $file, array $cfb, int $objectId): string'),
('private function firstZone(array $zoneLists, $name)','private function firstZone(array $zoneLists, string $name): ?array'),
('private function findZoneById(array $zoneLists, $name, $id)','private function findZoneById(array $zoneLists, string $name, int $id): ?array'),
('private function collectSiblingTree(array $directory, $index, array &$seen = []): array','private function collectSiblingTree(array $directory, int $index, array &$seen = []): array'),
('private function findEntryByNameAndType(array $directory, $name, $type)','private function findEntryByNameAndType(array $directory, string $name, int $type): ?array'),
('private function readChain($file, array $fat, $start, $size): string','private function readChain(string $file, array $fat, int $start, ?int $size): string'),
('private function sector($file, $sector): string','private function sector(string $file, int $sector): string'),
('private function u16($data, $offset): int','private function u16(string $data, int $offset): int'),
('private function u32($data, $offset): int','private function u32(string $data, int $offset): int'),
('private function u64($data, $offset): int','private function u64(string $data, int $offset): int'),
("        return unpack('v', substr($data, $offset, 2))[1];","        $value = unpack('v', substr($data, $offset, 2));\n        if ($value === false) {\n            throw new RuntimeException('Unable to unpack uint16.');\n        }\n\n        return $value[1];"),
("        return unpack('V', substr($data, $offset, 4))[1];","        $value = unpack('V', substr($data, $offset, 4));\n        if ($value === false) {\n            throw new RuntimeException('Unable to unpack uint32.');\n        }\n\n        return $value[1];"),
])
p=root/'Validator.php'; s=p.read_text(); a=s.find('    private function parseFdpcObjectPositions('); b=s.find('    private function parseEobj(', a)
if a!=-1 and b!=-1:
    s=s[:a]+s[b:]
else:
    print('Could not remove obsolete parser block',a,b)
p.write_text(s)
print('done')
