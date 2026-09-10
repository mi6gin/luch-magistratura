<?php

namespace App\Services;

use DateTimeInterface;
use Illuminate\Contracts\Cache\LockTimeoutException;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Cache;
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
    private const TEMPLATE_HELPER_ROWS = 5_000;

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
            ['05', 'Импорт', 'Выберите филиал и внесите его полный набор данных', 'Не меняйте названия листов и колонок', 'Файл заменит данные только активного филиала'],
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
            ? 'Это исследовательский пример: 8 товаров × 365 дней = 2 920 строк. Импорт применяется только к выбранному в интерфейсе филиалу.'
            : 'Это пустой шаблон полного набора данных одного филиала. Выберите нужный филиал перед загрузкой; сведения других филиалов не изменятся.');
        if ($withExample) {
            $guide->mergeCells('A25:E25')->setCellValue('A25', 'СЦЕНАРИИ В ИССЛЕДОВАТЕЛЬСКОМ ПРИМЕРЕ');
            $guide->fromArray([
                ['SKU', 'Сценарий', 'Товар', 'Что заложено в данные', 'Что проверяем'],
                ['SKU-1001', 'Стабильный', 'Молоко', 'Ровный спрос и слабый шум', 'Базовая точность'],
                ['SKU-1002', 'Недельная сезонность', 'Хлеб', 'Рост спроса в выходные', 'Работу сезонных моделей'],
                ['SKU-1003', 'Тренд', 'Яблоки', 'Постепенный рост в течение года', 'Реакцию на изменение уровня'],
                ['SKU-1004', 'Промо', 'Кофе', 'Акция на 5 дней каждые 4 недели', 'Использование промо-признака'],
                ['SKU-1005', 'Годовая сезонность', 'Мороженое', 'Летний пик и зимний минимум', 'Длинную сезонную зависимость'],
                ['SKU-1006', 'Прерывистый', 'Фильтр', 'Продажа примерно раз в 12 дней', 'Croston и sparse demand'],
                ['SKU-1007', 'Нерегулярный', 'Батарейки', 'Редкие крупные групповые заказы', 'Lumpy demand'],
                ['SKU-1008', 'Праздничный', 'Шоколад', 'Всплески в отмеченные праздники', 'Внешний календарный фактор'],
            ], '__EMPTY__', 'A26');
            $guide->getStyle('A25:E25')->applyFromArray([
                'font' => ['bold' => true, 'color' => ['rgb' => '46E6FF']],
                'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '10232F']],
            ]);
            $guide->getStyle('A26:E34')->getAlignment()->setWrapText(true)->setVertical(Alignment::VERTICAL_TOP);
            $guide->getStyle('A26:E26')->applyFromArray([
                'font' => ['bold' => true, 'color' => ['rgb' => '08131D']],
                'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => '46E6FF']],
            ]);
            for ($row = 27; $row <= 34; $row++) {
                $guide->getRowDimension($row)->setRowHeight(34);
                if ($row % 2 === 0) {
                    $guide->getStyle("A{$row}:E{$row}")->getFill()
                        ->setFillType(Fill::FILL_SOLID)->getStartColor()->setRGB('EAFBFF');
                }
            }
        }

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
        $productIds = range(1001, 1008);
        $startDate = new \DateTimeImmutable('2025-09-01');
        for ($day = 0; $day < 365; $day++) {
            $date = $startDate->modify("+{$day} days");
            $weekend = (int) $date->format('N') >= 6;
            foreach ($productIds as $productId) {
                $noise = (($day * (($productId % 5) + 2) + $productId) % 5) - 2;
                $promo = $productId === 1004 && $day % 28 < 5;
                $holiday = in_array($date->format('m-d'), ['01-01', '03-08', '05-09', '12-16'], true) ? 1 : 0;
                $quantity = match ($productId) {
                    1001 => 18 + $noise,
                    1002 => 30 + ($weekend ? 12 : 0) + $noise,
                    1003 => 8 + (int) floor($day / 24) + $noise,
                    1004 => 7 + ($promo ? 18 : 0) + $noise,
                    1005 => 6 + (int) round(14 * max(0, sin(2 * M_PI * ($day - 90) / 365))) + $noise,
                    1006 => $day % 12 === 0 ? 8 + ($day % 5) : 0,
                    1007 => in_array($day % 35, [0, 1], true) ? 28 + ($day % 11) : 0,
                    1008 => 5 + ($holiday ? 30 : 0) + ((int) $date->format('m') === 12 ? 5 : 0) + $noise,
                };
                $inStock = ! (($productId === 1002 && $day >= 319 && $day <= 321) || ($productId === 1004 && $day >= 190 && $day <= 192));
                $quantity = $inStock ? max($quantity, 0) : 0;
                $salesExamples[] = ["SKU-{$productId}", $date->format('Y-m-d'), $quantity, (int) $inStock, $holiday, (int) $promo];
            }
        }

        $examples = [
            'Товары' => [
                ['SKU-1001', 'Молоко 3,2% 1 л', 'Молочные продукты', 2, 620],
                ['SKU-1002', 'Хлеб пшеничный 500 г', 'Хлеб и выпечка', 1, 280],
                ['SKU-1003', 'Яблоки Голден 1 кг', 'Фрукты и овощи', 3, 890],
                ['SKU-1004', 'Кофе зерновой 500 г', 'Бакалея', 7, 4200],
                ['SKU-1005', 'Мороженое пломбир', 'Замороженные продукты', 4, 550],
                ['SKU-1006', 'Фильтр для принтера', 'Расходные материалы', 14, 6800],
                ['SKU-1007', 'Батарейки AA, 4 шт.', 'Хозяйственные товары', 10, 1450],
                ['SKU-1008', 'Шоколад подарочный', 'Кондитерские изделия', 5, 2300],
            ],
            'Продажи' => $salesExamples,
            'Остатки' => [
                ['SKU-1001', 'Главный склад', '2026-08-31', 42, 5],
                ['SKU-1002', 'Главный склад', '2026-08-31', 75, 10],
                ['SKU-1003', 'Главный склад', '2026-08-31', 28, 0],
                ['SKU-1004', 'Главный склад', '2026-08-31', 35, 4],
                ['SKU-1005', 'Главный склад', '2026-08-31', 52, 6],
                ['SKU-1006', 'Главный склад', '2026-08-31', 9, 1],
                ['SKU-1007', 'Главный склад', '2026-08-31', 18, 2],
                ['SKU-1008', 'Главный склад', '2026-08-31', 44, 5],
            ],
            'Поставки' => [
                ['PO-2026-081', 'SKU-1001', 60, '2026-09-03', 'подтверждена', 'ТОО Молочный дом'],
                ['PO-2026-082', 'SKU-1003', 35, '2026-09-05', 'в пути', 'ТОО Fresh Fruits'],
                ['PO-2026-083', 'SKU-1004', 24, '2026-09-07', 'подтверждена', 'ТОО Coffee Trade'],
                ['PO-2026-084', 'SKU-1006', 12, '2026-09-12', 'в пути', 'ТОО Office Supply'],
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

        $book->getSheetByName('Продажи')?->getStyle('B2:B'.self::TEMPLATE_HELPER_ROWS)->getNumberFormat()->setFormatCode('yyyy-mm-dd');
        $book->getSheetByName('Остатки')?->getStyle('C2:C'.self::TEMPLATE_HELPER_ROWS)->getNumberFormat()->setFormatCode('yyyy-mm-dd');
        $book->getSheetByName('Поставки')?->getStyle('D2:D'.self::TEMPLATE_HELPER_ROWS)->getNumberFormat()->setFormatCode('yyyy-mm-dd');
        foreach (['D', 'E', 'F'] as $column) {
            $validation = new DataValidation;
            $validation->setType(DataValidation::TYPE_LIST);
            $validation->setAllowBlank(false);
            $validation->setFormula1('"0,1"');
            $book->getSheetByName('Продажи')?->setDataValidation("{$column}2:{$column}".self::TEMPLATE_HELPER_ROWS, $validation);
        }
        $statusValidation = new DataValidation;
        $statusValidation->setType(DataValidation::TYPE_LIST);
        $statusValidation->setAllowBlank(false);
        $statusValidation->setFormula1('"подтверждена,в пути"');
        $book->getSheetByName('Поставки')?->setDataValidation('E2:E'.self::TEMPLATE_HELPER_ROWS, $statusValidation);

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

    public function preview(UploadedFile $file, ?int $branchId = null): array
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

        $branchId ??= 1;
        $payload = compact('branchId', 'productRows', 'salesRows', 'stockRows', 'supplyRows');
        $token = bin2hex(random_bytes(16));
        $directory = storage_path('app/branches/'.$branchId.'/import-previews');
        File::ensureDirectoryExists($directory);
        File::put($directory.DIRECTORY_SEPARATOR.$token.'.json', json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));

        $currentCounts = [
            'products' => Schema::hasTable('branch_products') ? DB::table('branch_products')->where('branch_id', $branchId)->count() : 0,
            'sales' => DB::table('sales_history')->where('branch_id', $branchId)->count(),
            'stocks' => DB::table('warehouse_stock')->where('branch_id', $branchId)->count(),
            'supplies' => DB::table('warehouse_in_transit')->where('branch_id', $branchId)->count(),
        ];
        $nextCounts = [
            'products' => count($productRows),
            'sales' => count($salesRows),
            'stocks' => count($stockRows),
            'supplies' => count($supplyRows),
        ];

        return [
            'token' => $token,
            'branch_id' => $branchId,
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

    public function commit(string $token, string $sourceName, ?int $branchId = null): array
    {
        $branchId ??= 1;
        try {
            return Cache::lock('inventory-import:branch:'.$branchId, 120)->block(
                1,
                fn (): array => $this->commitLocked($token, $sourceName, $branchId),
            );
        } catch (LockTimeoutException) {
            throw new InvalidArgumentException('Для этого филиала уже выполняется импорт. Дождитесь его завершения.');
        }
    }

    private function commitLocked(string $token, string $sourceName, int $branchId): array
    {
        if (preg_match('/^[a-f0-9]{32}$/', $token) !== 1) {
            throw new InvalidArgumentException('Некорректный идентификатор предварительной проверки.');
        }
        $path = storage_path('app/branches/'.$branchId.'/import-previews/'.$token.'.json');
        if (! File::isFile($path)) {
            throw new InvalidArgumentException('Предварительная проверка устарела. Загрузите файл ещё раз.');
        }
        $payload = json_decode((string) File::get($path), true, 512, JSON_THROW_ON_ERROR);
        if ((int) ($payload['branchId'] ?? 0) !== $branchId) {
            throw new InvalidArgumentException('Предварительная проверка принадлежит другому филиалу.');
        }
        $this->ensureImportSchema();

        $database = (string) config('database.connections.sqlite.database');
        $backupDirectory = storage_path('app/branches/'.$branchId.'/import-backups');
        File::ensureDirectoryExists($backupDirectory);
        $backup = $backupDirectory.'/inventory-before-'.now()->format('Ymd-His').'.sqlite';
        if (File::isFile($database)) {
            File::copy($database, $backup);
        }

        DB::transaction(function () use ($payload, $branchId): void {
            DB::table('sales_history')->where('branch_id', $branchId)->delete();
            DB::table('warehouse_stock')->where('branch_id', $branchId)->delete();
            DB::table('warehouse_in_transit')->where('branch_id', $branchId)->delete();
            DB::table('branch_products')->where('branch_id', $branchId)->delete();

            $productMap = [];
            foreach ($payload['productRows'] as $product) {
                $temporaryId = (int) $product['id'];
                $productId = DB::table('products')->where('sku', $product['sku'])->value('id');
                $catalog = ['sku' => $product['sku'], 'name' => $product['name'], 'category' => $product['category']];
                if ($productId === null) {
                    $productId = DB::table('products')->insertGetId($catalog + [
                        'lead_time' => $product['lead_time'], 'unit_price' => $product['unit_price'],
                    ]);
                } else {
                    DB::table('products')->where('id', $productId)->update($catalog);
                }
                $productMap[$temporaryId] = (int) $productId;
                DB::table('branch_products')->insert([
                    'branch_id' => $branchId, 'product_id' => $productId,
                    'lead_time' => $product['lead_time'], 'unit_price' => $product['unit_price'],
                    'active' => true, 'created_at' => now(), 'updated_at' => now(),
                ]);
            }
            $remap = static function (array $rows) use ($productMap, $branchId): array {
                return array_map(function (array $row) use ($productMap, $branchId): array {
                    $row['product_id'] = $productMap[(int) $row['product_id']];
                    $row['branch_id'] = $branchId;

                    return $row;
                }, $rows);
            };
            $payload['salesRows'] = $remap($payload['salesRows']);
            $payload['stockRows'] = $remap($payload['stockRows']);
            $payload['supplyRows'] = $remap($payload['supplyRows']);
            $payload['productRows'] = array_map(function (array $product) use ($productMap): array {
                $product['id'] = $productMap[(int) $product['id']];

                return $product;
            }, $payload['productRows']);
            foreach (array_chunk($payload['salesRows'], 500) as $chunk) {
                DB::table('sales_history')->insert($chunk);
            }
            DB::table('warehouse_stock')->insert($payload['stockRows']);
            if ($payload['supplyRows'] !== []) {
                DB::table('warehouse_in_transit')->insert($payload['supplyRows']);
            }
            $this->syncPlanningTables($payload, $branchId);
        });
        File::delete($path);

        $result = [
            'products' => count($payload['productRows']),
            'sales' => count($payload['salesRows']),
            'stocks' => count($payload['stockRows']),
            'supplies' => count($payload['supplyRows']),
        ];
        $historyDirectory = storage_path('app/branches/'.$branchId.'/import-history');
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

    private function syncPlanningTables(array $payload, int $branchId): void
    {
        if (! Schema::hasTable('warehouses')) {
            return;
        }

        $orderIdsToDelete = DB::table('purchase_orders')->where('branch_id', $branchId)->pluck('id');
        DB::table('purchase_order_lines')->whereIn('purchase_order_id', $orderIdsToDelete)->delete();
        DB::table('purchase_orders')->where('branch_id', $branchId)->delete();
        DB::table('product_planning_settings')->where('branch_id', $branchId)->delete();
        DB::table('inventory_snapshots')->where('branch_id', $branchId)->delete();
        DB::table('suppliers')->where('branch_id', $branchId)->delete();
        DB::table('warehouses')->where('branch_id', $branchId)->delete();

        $warehouseIds = [];
        foreach (array_values(array_unique(array_column($payload['stockRows'], 'warehouse'))) as $warehouse) {
            $warehouseIds[$warehouse] = DB::table('warehouses')->insertGetId([
                'code' => mb_strtoupper(substr(hash('sha256', $branchId.'|'.$warehouse), 0, 10)),
                'name' => $warehouse,
                'branch_id' => $branchId,
                'active' => true,
                'created_at' => now(),
                'updated_at' => now(),
            ]);
        }
        foreach ($payload['stockRows'] as $row) {
            DB::table('inventory_snapshots')->insert([
                'product_id' => $row['product_id'],
                'branch_id' => $branchId,
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
                'branch_id' => $branchId,
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
                    'order_number' => 'B'.$branchId.'-'.$row['order_number'],
                    'branch_id' => $branchId,
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
                'branch_id' => $branchId,
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
