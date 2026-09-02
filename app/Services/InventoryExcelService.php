<?php

namespace App\Services;

use DateTimeInterface;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Schema;
use InvalidArgumentException;
use PhpOffice\PhpSpreadsheet\Cell\Coordinate;
use PhpOffice\PhpSpreadsheet\Cell\DataValidation;
use PhpOffice\PhpSpreadsheet\IOFactory;
use PhpOffice\PhpSpreadsheet\RichText\RichText;
use PhpOffice\PhpSpreadsheet\Shared\Date;
use PhpOffice\PhpSpreadsheet\Spreadsheet;
use PhpOffice\PhpSpreadsheet\Style\Alignment;
use PhpOffice\PhpSpreadsheet\Style\Fill;
use PhpOffice\PhpSpreadsheet\Writer\Xlsx;
use Throwable;

class InventoryExcelService
{
    private const SHEETS = [
        'Товары' => ['SKU', 'Название', 'Категория', 'Срок поставки (дни)', 'Цена за единицу'],
        'Продажи' => ['SKU', 'Дата продажи', 'Продано', 'Был в наличии', 'Праздник', 'Промо'],
        'Остатки' => ['SKU', 'Склад', 'Дата состояния', 'Доступный остаток', 'Зарезервировано'],
        'Поставки' => ['Номер поставки', 'SKU', 'Количество', 'Ожидаемая дата', 'Статус', 'Поставщик'],
    ];

    public function createTemplate(string $path, bool $withExample = false): void
    {
        $book = new Spreadsheet;
        $book->removeSheetByIndex(0);

        $guide = $book->createSheet();
        $guide->setTitle('Инструкция');
        $guide->setShowGridlines(false);
        $guide->getTabColor()->setRGB('46E6FF');
        $guide->mergeCells('A1:E2');
        $guide->setCellValue('A1', 'RAYVENTORY  /  DATA STARTER KIT');
        $guide->mergeCells('A3:E3');
        $guide->setCellValue('A3', 'Понятный Excel → точный прогноз запасов');
        $guide->mergeCells('A5:B7');
        $guide->setCellValue('A5', "90 ДНЕЙ\nминимум для базового прогноза");
        $guide->mergeCells('C5:D7');
        $guide->setCellValue('C5', "12 МЕСЯЦЕВ\nрекомендуется для сезонности");
        $guide->setCellValue('E5', "1 СТРОКА\n= 1 товар\nза 1 день");
        $guide->mergeCells('A9:E9');
        $guide->setCellValue('A9', 'КАК ЭТО РАБОТАЕТ');
        $guide->fromArray([
            ['01', 'Товары', 'Создайте каталог', 'Одна строка на товар', 'ID должен быть уникальным'],
            ['02', 'Продажи', 'Добавьте ежедневную историю', 'Минимум 90 дней; лучше 12 месяцев', 'Пропущенные даты ухудшают прогноз'],
            ['03', 'Остатки', 'Укажите состояние на сегодня', 'Ровно одна строка на товар', 'Количество не может быть отрицательным'],
            ['04', 'Поставки', 'Добавьте ожидаемые поступления', 'Лист необязательный', 'Укажите дату, статус и поставщика'],
            ['05', 'Импорт', 'Удалите тестовые строки и внесите свои', 'Не меняйте названия листов и колонок', 'Загрузите .xlsx в разделе «Склад»'],
        ], '__EMPTY__', 'A10');
        $guide->mergeCells('A17:E17');
        $guide->setCellValue('A17', 'ЧТО ОЗНАЧАЮТ 0 И 1 НА ЛИСТЕ «ПРОДАЖИ»');
        $guide->fromArray([
            ['Поле', '0 означает', '1 означает', 'Пример', 'Зачем это модели'],
            ['Был в наличии', 'Товара не было', 'Товар был доступен', 'Продажи 0 при наличии 0 ≠ отсутствие спроса', 'Восстанавливает скрытый спрос'],
            ['Праздник', 'Обычный день', 'Праздничный день', '8 марта, Новый год', 'Учитывает календарный всплеск'],
            ['Промо', 'Обычная цена', 'Акция или скидка', '−15% на выходных', 'Не принимает промо-рост за обычный спрос'],
        ], '__EMPTY__', 'A18');
        $guide->mergeCells('A23:E23');
        $guide->setCellValue('A23', $withExample
            ? 'Это заполненный пример: 3 товара × 365 дней = 1 095 строк продаж за 12 месяцев. Его можно сразу проверить на сайте.'
            : 'Это пустой рабочий шаблон. Не меняйте названия листов и колонок; заполните его своими данными и загрузите на сайте.');

        $guide->getStyle('A1:E2')->applyFromArray([
            'font' => ['bold' => true, 'size' => 20, 'color' => ['rgb' => 'FFFFFF']],
            'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '08131D']],
            'alignment' => ['horizontal' => Alignment::HORIZONTAL_LEFT, 'vertical' => Alignment::VERTICAL_CENTER],
        ]);
        $guide->getStyle('A3:E3')->applyFromArray([
            'font' => ['bold' => true, 'size' => 12, 'color' => ['rgb' => '385466']],
        ]);
        foreach (['A5:B7', 'C5:D7', 'E5:E7'] as $card) {
            $guide->getStyle($card)->applyFromArray([
                'font' => ['bold' => true, 'size' => 13, 'color' => ['rgb' => '08131D']],
                'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => 'EAFBFF']],
                'alignment' => ['wrapText' => true, 'horizontal' => Alignment::HORIZONTAL_CENTER, 'vertical' => Alignment::VERTICAL_CENTER],
                'borders' => ['outline' => ['style' => 'thin', 'color' => ['rgb' => 'B9EDF4']]],
            ]);
        }
        foreach (['A9:E9', 'A17:E17'] as $section) {
            $guide->getStyle($section)->applyFromArray([
                'font' => ['bold' => true, 'color' => ['rgb' => '46E6FF']],
                'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '10232F']],
            ]);
        }
        $guide->getStyle('A10:E14')->getAlignment()->setWrapText(true)->setVertical(Alignment::VERTICAL_TOP);
        $guide->getStyle('A10:A14')->getFont()->setBold(true)->getColor()->setRGB('FF7440');
        $guide->getStyle('A18:E18')->applyFromArray([
            'font' => ['bold' => true, 'color' => ['rgb' => '08131D']],
            'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '46E6FF']],
        ]);
        $guide->getStyle('A19:E21')->getAlignment()->setWrapText(true)->setVertical(Alignment::VERTICAL_TOP);
        $guide->getStyle('A23:E23')->applyFromArray([
            'font' => ['bold' => true, 'color' => ['rgb' => '7A3B20']],
            'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => 'FFF0E8']],
            'alignment' => ['wrapText' => true, 'vertical' => Alignment::VERTICAL_CENTER],
        ]);
        $guide->getRowDimension(23)->setRowHeight(42);
        foreach (['A' => 10, 'B' => 25, 'C' => 37, 'D' => 33, 'E' => 40] as $column => $width) {
            $guide->getColumnDimension($column)->setWidth($width);
        }
        $guide->freezePane('A10');

        $salesExamples = [];
        $baseDemand = [1001 => 18, 1002 => 30, 1003 => 13];
        $startDate = new \DateTimeImmutable('2025-09-01');
        for ($day = 0; $day < 365; $day++) {
            $date = $startDate->modify("+{$day} days");
            $weekend = (int) $date->format('N') >= 6;
            foreach ($baseDemand as $productId => $base) {
                $dayOfMonth = (int) $date->format('j');
                $promo = in_array($dayOfMonth, [8, 9, 22, 23], true) && $productId !== 1003;
                $holiday = in_array($date->format('m-d'), ['01-01', '03-08', '05-09', '12-16'], true) ? 1 : 0;
                $inStock = ! ($productId === 1002 && in_array($date->format('Y-m-d'), ['2026-07-17', '2026-07-18'], true));
                $quantity = $inStock ? $base + (($day * ($productId % 7)) % 7) + ($weekend ? 4 : 0) + ($promo ? 8 : 0) : 0;
                $salesExamples[] = ["SKU-{$productId}", $date->format('Y-m-d'), $quantity, (int) $inStock, $holiday, (int) $promo];
            }
        }

        $examples = [
            'Товары' => [
                ['SKU-1001', 'Молоко 3,2% 1 л', 'Молочные продукты', 2, 620],
                ['SKU-1002', 'Хлеб пшеничный 500 г', 'Хлеб и выпечка', 1, 280],
                ['SKU-1003', 'Яблоки Голден 1 кг', 'Фрукты и овощи', 3, 890],
            ],
            'Продажи' => $salesExamples,
            'Остатки' => [
                ['SKU-1001', 'Главный склад', '2026-08-31', 42, 5],
                ['SKU-1002', 'Главный склад', '2026-08-31', 75, 10],
                ['SKU-1003', 'Главный склад', '2026-08-31', 28, 0],
            ],
            'Поставки' => [
                ['PO-2026-081', 'SKU-1001', 60, '2026-09-03', 'подтверждена', 'ТОО Молочный дом'],
                ['PO-2026-082', 'SKU-1003', 35, '2026-09-05', 'в пути', 'ТОО Fresh Fruits'],
            ],
        ];

        if (! $withExample) {
            $examples = array_fill_keys(array_keys(self::SHEETS), []);
        }

        foreach (self::SHEETS as $name => $headers) {
            $sheet = $book->createSheet();
            $sheet->setTitle($name);
            $sheet->setShowGridlines(false);
            $sheet->getTabColor()->setRGB(match ($name) {
                'Товары' => 'A78BFA',
                'Продажи' => '46E6FF',
                'Остатки' => 'B9F85B',
                default => 'FFB454',
            });
            $lastColumn = Coordinate::stringFromColumnIndex(count($headers));
            $sheet->fromArray($headers, '__EMPTY__', 'A1');
            $sheet->fromArray($examples[$name], '__EMPTY__', 'A2');
            $sheet->freezePane('A2');
            $sheet->setAutoFilter("A1:{$lastColumn}1");
            $sheet->getStyle("A1:{$lastColumn}1")->applyFromArray([
                'font' => ['bold' => true, 'color' => ['rgb' => 'FFFFFF']],
                'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '10232F']],
                'alignment' => ['horizontal' => Alignment::HORIZONTAL_CENTER, 'vertical' => Alignment::VERTICAL_CENTER],
            ]);
            $sheet->getRowDimension(1)->setRowHeight(30);
            $exampleLastRow = count($examples[$name]) + 1;
            if ($exampleLastRow >= 2) {
                $sheet->getStyle("A2:{$lastColumn}{$exampleLastRow}")->getFill()
                    ->setFillType(Fill::FILL_SOLID)->getStartColor()->setRGB('F4FBFC');
                for ($row = 3; $row <= $exampleLastRow; $row += 2) {
                    $sheet->getStyle("A{$row}:{$lastColumn}{$row}")->getFill()
                        ->setFillType(Fill::FILL_SOLID)->getStartColor()->setRGB('EAFBFF');
                }
                $sheet->getStyle("A2:{$lastColumn}{$exampleLastRow}")->getAlignment()
                    ->setVertical(Alignment::VERTICAL_CENTER);
            }
            foreach (range('A', $lastColumn) as $column) {
                $sheet->getColumnDimension($column)->setAutoSize(true);
            }
        }

        $headerHints = [
            'Товары' => [
                'SKU' => 'Постоянный уникальный код товара из вашей учётной системы. Этот же SKU используйте на остальных листах.',
                'Название' => 'Понятное пользователю название товара.',
                'Категория' => 'Категория для аналитики и группировки на дашборде.',
                'Срок поставки (дни)' => 'Сколько календарных дней проходит от заказа до поступления товара.',
                'Цена за единицу' => 'Цена одной единицы товара в тенге, только число без символа ₸.',
            ],
            'Продажи' => [
                'SKU' => 'SKU с листа «Товары». Для хорошего прогноза нужен каждый товар за каждый день периода.',
                'Дата продажи' => 'Дата в формате ГГГГ-ММ-ДД. В заполненном примере дан непрерывный период за 12 месяцев.',
                'Продано' => 'Фактически проданное количество за день.',
                'Был в наличии' => '1 — товар был доступен; 0 — товара не было, поэтому нулевые продажи не равны нулевому спросу.',
                'Праздник' => '1 — праздничный или особый календарный день; иначе 0.',
                'Промо' => '1 — действовала акция/скидка; иначе 0.',
            ],
            'Остатки' => [
                'SKU' => 'SKU с листа «Товары». Для одного склада каждый товар должен встретиться ровно один раз.',
                'Склад' => 'Название склада или торговой точки.',
                'Дата состояния' => 'Дата, на которую зафиксированы остатки, в формате ГГГГ-ММ-ДД.',
                'Доступный остаток' => 'Фактическое количество товара на складе.',
                'Зарезервировано' => 'Количество, уже зарезервированное под заказы клиентов.',
            ],
            'Поставки' => [
                'Номер поставки' => 'Уникальный номер заказа поставщику или поставки.',
                'SKU' => 'SKU с листа «Товары».',
                'Количество' => 'Заказанное, но ещё не принятое количество.',
                'Ожидаемая дата' => 'Плановая дата поступления в формате ГГГГ-ММ-ДД.',
                'Статус' => 'Допустимые значения: подтверждена, в пути.',
                'Поставщик' => 'Название поставщика.',
            ],
        ];
        foreach ($headerHints as $sheetName => $hints) {
            $sheet = $book->getSheetByName($sheetName);
            foreach (array_values(self::SHEETS[$sheetName]) as $index => $header) {
                $coordinate = Coordinate::stringFromColumnIndex($index + 1).'1';
                $comment = $sheet?->getComment($coordinate);
                $comment?->setAuthor('Rayventory')->setText(new RichText);
                $comment?->getText()->createText($hints[$header]);
            }
        }

        $book->getSheetByName('Продажи')?->getStyle('B2:B1000')->getNumberFormat()->setFormatCode('yyyy-mm-dd');
        $book->getSheetByName('Остатки')?->getStyle('C2:C1000')->getNumberFormat()->setFormatCode('yyyy-mm-dd');
        $book->getSheetByName('Поставки')?->getStyle('D2:D1000')->getNumberFormat()->setFormatCode('yyyy-mm-dd');
        foreach (['D', 'E', 'F'] as $column) {
            $validation = new DataValidation;
            $validation->setType(DataValidation::TYPE_LIST);
            $validation->setAllowBlank(false);
            $validation->setFormula1('"0,1"');
            $book->getSheetByName('Продажи')?->setDataValidation("{$column}2:{$column}1000", $validation);
        }
        $statusValidation = new DataValidation;
        $statusValidation->setType(DataValidation::TYPE_LIST);
        $statusValidation->setAllowBlank(false);
        $statusValidation->setFormula1('"подтверждена,в пути"');
        $book->getSheetByName('Поставки')?->setDataValidation('E2:E1000', $statusValidation);

        $book->setActiveSheetIndexByName('Инструкция');
        (new Xlsx($book))->save($path);
        $book->disconnectWorksheets();
    }

    public function createPurchasePlanExport(string $path, array $items, ?float $budget = null): void
    {
        $book = new Spreadsheet;
        $summary = $book->getActiveSheet();
        $summary->setTitle('Сводка');
        $summary->setShowGridlines(false);
        $summary->mergeCells('A1:D2')->setCellValue('A1', 'RAYVENTORY  /  ПЛАН ЗАКУПОК');
        $summary->fromArray([
            ['Дата формирования', now()->format('Y-m-d H:i')],
            ['Бюджет, ₸', $budget],
            ['Позиций', count($items)],
            ['Единиц к заказу', '=SUM(\'Заказ\'!F2:F'.(count($items) + 1).')'],
            ['Итого, ₸', '=SUM(\'Заказ\'!H2:H'.(count($items) + 1).')'],
        ], null, 'A4');
        $summary->getStyle('A1:D2')->applyFromArray([
            'font' => ['bold' => true, 'size' => 20, 'color' => ['rgb' => 'FFFFFF']],
            'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '08131D']],
            'alignment' => ['vertical' => Alignment::VERTICAL_CENTER],
        ]);
        $summary->getStyle('A4:A8')->getFont()->setBold(true);
        $summary->getStyle('B5:B8')->getNumberFormat()->setFormatCode('#,##0');
        $summary->getColumnDimension('A')->setWidth(24);
        $summary->getColumnDimension('B')->setWidth(22);

        $order = $book->createSheet();
        $order->setTitle('Заказ');
        $order->setShowGridlines(false);
        $headers = ['Приоритет', 'SKU', 'Товар', 'Поставщик', 'Заказать до', 'Количество', 'Цена за единицу, ₸', 'Сумма, ₸', 'Ожидаемый дефицит', 'Комментарий'];
        $order->fromArray($headers, null, 'A1');
        foreach (array_values($items) as $index => $item) {
            $row = $index + 2;
            $order->fromArray([
                $index + 1,
                $item['sku'],
                $item['product_name'],
                $item['supplier'] ?: 'Не указан',
                $item['best_order_date'],
                $item['quantity'],
                $item['unit_price'],
                "=F{$row}*G{$row}",
                $item['stockout_date'],
                $item['quantity'] < $item['recommended_quantity'] ? 'Количество ограничено бюджетом' : 'Рекомендация модели',
            ], null, "A{$row}");
        }
        $lastRow = count($items) + 1;
        $order->freezePane('A2');
        $order->setAutoFilter("A1:J{$lastRow}");
        $order->getStyle('A1:J1')->applyFromArray([
            'font' => ['bold' => true, 'color' => ['rgb' => 'FFFFFF']],
            'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '10232F']],
            'alignment' => ['horizontal' => Alignment::HORIZONTAL_CENTER, 'vertical' => Alignment::VERTICAL_CENTER],
        ]);
        $order->getRowDimension(1)->setRowHeight(30);
        if ($lastRow >= 2) {
            $order->getStyle("A2:J{$lastRow}")->getAlignment()->setVertical(Alignment::VERTICAL_CENTER);
            $order->getStyle("F2:F{$lastRow}")->getNumberFormat()->setFormatCode('#,##0');
            $order->getStyle("G2:H{$lastRow}")->getNumberFormat()->setFormatCode('#,##0');
            $order->getStyle("E2:E{$lastRow}")->getNumberFormat()->setFormatCode('yyyy-mm-dd');
            $order->getStyle("I2:I{$lastRow}")->getNumberFormat()->setFormatCode('yyyy-mm-dd');
        }
        foreach (['A' => 11, 'B' => 16, 'C' => 34, 'D' => 25, 'E' => 16, 'F' => 14, 'G' => 20, 'H' => 18, 'I' => 20, 'J' => 32] as $column => $width) {
            $order->getColumnDimension($column)->setWidth($width);
        }
        $order->getStyle("C2:D{$lastRow}")->getAlignment()->setWrapText(true);
        $order->getStyle("J2:J{$lastRow}")->getAlignment()->setWrapText(true);

        $book->setActiveSheetIndexByName('Сводка');
        (new Xlsx($book))->save($path);
        $book->disconnectWorksheets();
    }

    public function preview(UploadedFile $file): array
    {
        try {
            $reader = IOFactory::createReaderForFile($file->getRealPath());
            $reader->setReadDataOnly(true);
            $book = $reader->load($file->getRealPath());
        } catch (Throwable $exception) {
            throw new InvalidArgumentException('Не удалось прочитать Excel-файл. Проверьте, что это корректный .xlsx.', 0, $exception);
        }

        try {
            $products = $this->readSheet($book, 'Товары', self::SHEETS['Товары'], 5);
            $sales = $this->readSheet($book, 'Продажи', self::SHEETS['Продажи'], 6);
            $stocks = $this->readSheet($book, 'Остатки', self::SHEETS['Остатки'], 5);
            $supplies = $this->readSheet($book, 'Поставки', self::SHEETS['Поставки'], 6, true);
        } finally {
            $book->disconnectWorksheets();
        }

        if ($products === []) {
            throw new InvalidArgumentException('Лист «Товары» должен содержать хотя бы одну строку данных.');
        }
        if ($sales === []) {
            throw new InvalidArgumentException('Лист «Продажи» должен содержать историю продаж.');
        }

        $productRows = [];
        $productIds = [];
        foreach ($products as $index => $row) {
            $line = $index + 2;
            $sku = $this->sku($row[0], "Товары, строка {$line}: SKU");
            if (isset($productIds[$sku])) {
                throw new InvalidArgumentException("Товары, строка {$line}: повторяется SKU {$sku}.");
            }
            $id = count($productRows) + 1;
            $productIds[$sku] = $id;
            $productRows[] = [
                'id' => $id,
                'sku' => $sku,
                'name' => $this->requiredText($row[1], "Товары, строка {$line}: название"),
                'category' => $this->requiredText($row[2], "Товары, строка {$line}: категория"),
                'lead_time' => $this->nonNegativeInt($row[3], "Товары, строка {$line}: срок поставки"),
                'unit_price' => $this->nonNegativeNumber($row[4], "Товары, строка {$line}: цена"),
            ];
        }

        $salesRows = [];
        foreach ($sales as $index => $row) {
            $line = $index + 2;
            $id = $this->knownSku($row[0], $productIds, "Продажи, строка {$line}");
            $salesRows[] = [
                'product_id' => $id,
                'sale_date' => $this->date($row[1], "Продажи, строка {$line}: дата"),
                'quantity_sold' => $this->nonNegativeInt($row[2], "Продажи, строка {$line}: продано"),
                'in_stock' => $this->flag($row[3], "Продажи, строка {$line}: был в наличии"),
                'is_holiday' => $this->flag($row[4], "Продажи, строка {$line}: праздник"),
                'is_promo' => $this->flag($row[5], "Продажи, строка {$line}: промо"),
            ];
        }

        $stockRows = [];
        $seenStock = [];
        foreach ($stocks as $index => $row) {
            $line = $index + 2;
            $sku = $this->sku($row[0], "Остатки, строка {$line}: SKU");
            $id = $this->knownSku($sku, $productIds, "Остатки, строка {$line}");
            $warehouse = $this->requiredText($row[1], "Остатки, строка {$line}: склад");
            $key = $sku;
            if (isset($seenStock[$key])) {
                throw new InvalidArgumentException("Остатки, строка {$line}: SKU {$sku} повторяется. Текущая версия поддерживает один склад на товар.");
            }
            $seenStock[$key] = true;
            $available = $this->nonNegativeInt($row[3], "Остатки, строка {$line}: доступный остаток");
            $reserved = $this->nonNegativeInt($row[4], "Остатки, строка {$line}: зарезервировано");
            if ($reserved > $available) {
                throw new InvalidArgumentException("Остатки, строка {$line}: зарезервировано не может превышать доступный остаток.");
            }
            $stockRows[] = [
                'product_id' => $id,
                'current_quantity' => $available - $reserved,
                'warehouse' => $warehouse,
                'as_of_date' => $this->date($row[2], "Остатки, строка {$line}: дата состояния"),
                'reserved_quantity' => $reserved,
            ];
        }
        foreach ($productIds as $sku => $id) {
            if (! collect($stockRows)->contains('product_id', $id)) {
                throw new InvalidArgumentException("Лист «Остатки»: отсутствует SKU {$sku}.");
            }
        }

        $supplyRows = [];
        $seenSupply = [];
        foreach ($supplies as $index => $row) {
            $line = $index + 2;
            $orderNumber = $this->requiredText($row[0], "Поставки, строка {$line}: номер поставки");
            $id = $this->knownSku($row[1], $productIds, "Поставки, строка {$line}");
            $key = (string) $id;
            if (isset($seenSupply[$key])) {
                throw new InvalidArgumentException("Поставки, строка {$line}: для одного SKU пока поддерживается одна активная поставка.");
            }
            $seenSupply[$key] = true;
            $status = mb_strtolower($this->requiredText($row[4], "Поставки, строка {$line}: статус"));
            if (! in_array($status, ['подтверждена', 'в пути'], true)) {
                throw new InvalidArgumentException("Поставки, строка {$line}: статус должен быть «подтверждена» или «в пути».");
            }
            $supplyRows[] = [
                'product_id' => $id,
                'in_transit_quantity' => $this->nonNegativeInt($row[2], "Поставки, строка {$line}: количество"),
                'order_number' => $orderNumber,
                'expected_date' => $this->date($row[3], "Поставки, строка {$line}: ожидаемая дата"),
                'status' => $status,
                'supplier' => $this->requiredText($row[5], "Поставки, строка {$line}: поставщик"),
            ];
        }

        $dates = array_column($salesRows, 'sale_date');
        sort($dates);
        $periodStart = $dates[0];
        $periodEnd = $dates[array_key_last($dates)];
        $periodDays = (new \DateTimeImmutable($periodStart))->diff(new \DateTimeImmutable($periodEnd))->days + 1;
        $warnings = [];
        if ($periodDays < 90) {
            $warnings[] = 'История короче 90 дней: прогноз будет иметь низкую уверенность.';
        } elseif ($periodDays < 365) {
            $warnings[] = 'История короче 12 месяцев: сезонность может быть определена неточно.';
        }

        $payload = compact('productRows', 'salesRows', 'stockRows', 'supplyRows');
        $token = bin2hex(random_bytes(16));
        $directory = storage_path('app/import-previews');
        File::ensureDirectoryExists($directory);
        File::put($directory.DIRECTORY_SEPARATOR.$token.'.json', json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));

        $currentCounts = collect([
            'products' => 'products',
            'sales' => 'sales_history',
            'stocks' => 'warehouse_stock',
            'supplies' => 'warehouse_in_transit',
        ])->map(fn (string $table): int => Schema::hasTable($table) ? DB::table($table)->count() : 0)->all();
        $nextCounts = [
            'products' => count($productRows),
            'sales' => count($salesRows),
            'stocks' => count($stockRows),
            'supplies' => count($supplyRows),
        ];

        return [
            'token' => $token,
            'counts' => $nextCounts,
            'impact' => collect($nextCounts)->map(fn (int $next, string $key): array => [
                'current' => $currentCounts[$key],
                'next' => $next,
                'delta' => $next - $currentCounts[$key],
            ])->all(),
            'period' => ['start' => $periodStart, 'end' => $periodEnd, 'days' => $periodDays],
            'warehouses' => array_values(array_unique(array_column($stockRows, 'warehouse'))),
            'warnings' => $warnings,
            'sample' => array_slice($productRows, 0, 5),
            'mapping' => collect(self::SHEETS)->map(fn (array $headers) => array_combine($headers, $headers))->all(),
        ];
    }

    public function commit(string $token, string $sourceName): array
    {
        if (preg_match('/^[a-f0-9]{32}$/', $token) !== 1) {
            throw new InvalidArgumentException('Некорректный идентификатор предварительной проверки.');
        }
        $path = storage_path('app/import-previews/'.$token.'.json');
        if (! File::isFile($path)) {
            throw new InvalidArgumentException('Предварительная проверка устарела. Загрузите файл ещё раз.');
        }
        $payload = json_decode((string) File::get($path), true, 512, JSON_THROW_ON_ERROR);
        $this->ensureImportSchema();

        $database = (string) config('database.connections.sqlite.database');
        $backupDirectory = storage_path('app/import-backups');
        File::ensureDirectoryExists($backupDirectory);
        $backup = $backupDirectory.'/inventory-before-'.now()->format('Ymd-His').'.sqlite';
        if (File::isFile($database)) {
            File::copy($database, $backup);
        }

        DB::transaction(function () use ($payload): void {
            DB::table('sales_history')->delete();
            DB::table('warehouse_stock')->delete();
            DB::table('warehouse_in_transit')->delete();
            DB::table('products')->delete();
            DB::table('products')->insert($payload['productRows']);
            foreach (array_chunk($payload['salesRows'], 500) as $chunk) {
                DB::table('sales_history')->insert($chunk);
            }
            DB::table('warehouse_stock')->insert($payload['stockRows']);
            if ($payload['supplyRows'] !== []) {
                DB::table('warehouse_in_transit')->insert($payload['supplyRows']);
            }
            $this->syncPlanningTables($payload);
        });
        File::delete($path);

        $result = [
            'products' => count($payload['productRows']),
            'sales' => count($payload['salesRows']),
            'stocks' => count($payload['stockRows']),
            'supplies' => count($payload['supplyRows']),
        ];
        $historyDirectory = storage_path('app/import-history');
        File::ensureDirectoryExists($historyDirectory);
        File::put($historyDirectory.'/'.now()->format('Ymd-His').'-'.$token.'.json', json_encode([
            'imported_at' => now()->toIso8601String(),
            'source' => basename($sourceName),
            'counts' => $result,
            'backup' => basename($backup),
        ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR));

        return $result;
    }

    private function readSheet(Spreadsheet $book, string $name, array $headers, int $columns, bool $optional = false): array
    {
        $sheet = $book->getSheetByName($name);
        if ($sheet === null) {
            if ($optional) {
                return [];
            }
            throw new InvalidArgumentException("В файле отсутствует обязательный лист «{$name}».");
        }
        $lastColumn = Coordinate::stringFromColumnIndex($columns);
        $actualHeaders = $sheet->rangeToArray("A1:{$lastColumn}1", null, true, false)[0];
        if ($actualHeaders !== $headers) {
            throw new InvalidArgumentException("Лист «{$name}»: заголовки изменены. Используйте исходный шаблон.");
        }
        if ($sheet->getHighestDataRow() > 100001) {
            throw new InvalidArgumentException("Лист «{$name}» содержит больше 100 000 строк.");
        }
        if ($sheet->getHighestDataRow() < 2) {
            return [];
        }
        $rows = $sheet->rangeToArray("A2:{$lastColumn}".$sheet->getHighestDataRow(), null, false, false);

        return array_values(array_filter($rows, fn (array $row) => collect($row)->contains(fn ($value) => $value !== null && $value !== '')));
    }

    private function knownSku(mixed $value, array $ids, string $context): int
    {
        $sku = $this->sku($value, "{$context}: SKU");
        if (! isset($ids[$sku])) {
            throw new InvalidArgumentException("{$context}: SKU {$sku} отсутствует на листе «Товары».");
        }

        return $ids[$sku];
    }

    private function sku(mixed $value, string $field): string
    {
        $sku = mb_strtoupper(trim((string) $value));
        if ($sku === '' || mb_strlen($sku) > 80 || preg_match('/^[\p{L}\p{N}._\/-]+$/u', $sku) !== 1) {
            throw new InvalidArgumentException("{$field} должен содержать до 80 букв, цифр и символов . _ / -.");
        }

        return $sku;
    }

    private function ensureImportSchema(): void
    {
        if (! Schema::hasColumn('products', 'sku')) {
            Schema::table('products', fn ($table) => $table->string('sku', 80)->nullable());
        }
        if (! Schema::hasColumn('warehouse_stock', 'warehouse')) {
            Schema::table('warehouse_stock', function ($table): void {
                $table->string('warehouse')->nullable();
                $table->date('as_of_date')->nullable();
                $table->integer('reserved_quantity')->default(0);
            });
        }
        if (! Schema::hasColumn('warehouse_in_transit', 'order_number')) {
            Schema::table('warehouse_in_transit', function ($table): void {
                $table->string('order_number')->nullable();
                $table->date('expected_date')->nullable();
                $table->string('status')->nullable();
                $table->string('supplier')->nullable();
            });
        }
    }

    private function syncPlanningTables(array $payload): void
    {
        if (! Schema::hasTable('warehouses')) {
            return;
        }

        DB::table('purchase_order_lines')->delete();
        DB::table('purchase_orders')->delete();
        DB::table('product_planning_settings')->delete();
        DB::table('inventory_snapshots')->delete();
        DB::table('suppliers')->delete();
        DB::table('warehouses')->delete();

        $warehouseIds = [];
        foreach (array_values(array_unique(array_column($payload['stockRows'], 'warehouse'))) as $warehouse) {
            $warehouseIds[$warehouse] = DB::table('warehouses')->insertGetId([
                'code' => mb_strtoupper(substr(hash('sha256', $warehouse), 0, 10)),
                'name' => $warehouse,
                'active' => true,
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }
        foreach ($payload['stockRows'] as $row) {
            DB::table('inventory_snapshots')->insert([
                'product_id' => $row['product_id'],
                'warehouse_id' => $warehouseIds[$row['warehouse']],
                'snapshot_date' => $row['as_of_date'],
                'available_quantity' => $row['current_quantity'] + $row['reserved_quantity'],
                'reserved_quantity' => $row['reserved_quantity'],
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }

        $supplierIds = [];
        foreach (array_values(array_unique(array_column($payload['supplyRows'], 'supplier'))) as $supplier) {
            $supplierIds[$supplier] = DB::table('suppliers')->insertGetId([
                'name' => $supplier,
                'currency' => 'KZT',
                'default_lead_time_days' => 7,
                'minimum_order_value' => 0,
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }

        $orderIds = [];
        foreach ($payload['supplyRows'] as $row) {
            if (! isset($orderIds[$row['order_number']])) {
                $orderIds[$row['order_number']] = DB::table('purchase_orders')->insertGetId([
                    'order_number' => $row['order_number'],
                    'supplier_id' => $supplierIds[$row['supplier']],
                    'warehouse_id' => reset($warehouseIds) ?: null,
                    'status' => $row['status'] === 'в пути' ? 'in_transit' : 'confirmed',
                    'ordered_at' => null,
                    'expected_at' => $row['expected_date'],
                    'received_at' => null,
                    'created_at' => now(),
                    'updated_at' => now(),
                ]);
            }
            DB::table('purchase_order_lines')->insert([
                'purchase_order_id' => $orderIds[$row['order_number']],
                'product_id' => $row['product_id'],
                'ordered_quantity' => $row['in_transit_quantity'],
                'received_quantity' => 0,
                'unit_cost' => 0,
                'expected_at' => $row['expected_date'],
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }

        $supplierByProduct = [];
        foreach ($payload['supplyRows'] as $row) {
            $supplierByProduct[$row['product_id']] = $supplierIds[$row['supplier']];
        }
        foreach ($payload['productRows'] as $product) {
            DB::table('product_planning_settings')->insert([
                'product_id' => $product['id'],
                'supplier_id' => $supplierByProduct[$product['id']] ?? null,
                'safety_stock_days' => 14,
                'target_cover_days' => 45,
                'minimum_order_quantity' => 1,
                'pack_size' => 1,
                'replenishable' => true,
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }
    }

    private function nonNegativeInt(mixed $value, string $field): int
    {
        if (filter_var($value, FILTER_VALIDATE_INT) === false || (int) $value < 0) {
            throw new InvalidArgumentException("{$field} должен быть целым неотрицательным числом.");
        }

        return (int) $value;
    }

    private function nonNegativeNumber(mixed $value, string $field): float
    {
        if (! is_numeric($value) || ! is_finite((float) $value) || (float) $value < 0) {
            throw new InvalidArgumentException("{$field} должна быть неотрицательным числом.");
        }

        return (float) $value;
    }

    private function requiredText(mixed $value, string $field): string
    {
        $text = trim((string) $value);
        if ($text === '' || mb_strlen($text) > 255) {
            throw new InvalidArgumentException("{$field} не должно быть пустым или длиннее 255 символов.");
        }

        return $text;
    }

    private function flag(mixed $value, string $field): int
    {
        if (! in_array($value, [0, 1, '0', '1'], true)) {
            throw new InvalidArgumentException("{$field} должно содержать 0 или 1.");
        }

        return (int) $value;
    }

    private function date(mixed $value, string $field): string
    {
        if ($value instanceof DateTimeInterface) {
            return $value->format('Y-m-d');
        }
        if (is_numeric($value)) {
            try {
                return Date::excelToDateTimeObject((float) $value)->format('Y-m-d');
            } catch (Throwable) {
                // Continue to the common validation error.
            }
        }
        $text = trim((string) $value);
        $date = \DateTimeImmutable::createFromFormat('!Y-m-d', $text);
        if ($date === false || $date->format('Y-m-d') !== $text) {
            throw new InvalidArgumentException("{$field} должна быть в формате ГГГГ-ММ-ДД.");
        }

        return $text;
    }
}
