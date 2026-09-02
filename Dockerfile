FROM php:8.5-cli

RUN apt-get update \
    && apt-get install -y --no-install-recommends git unzip libonig-dev libpng-dev libsqlite3-dev libzip-dev python3 python3-pip \
    && docker-php-ext-install gd mbstring pdo_sqlite zip \
    && rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer
WORKDIR /var/www/html
ENV SESSION_DRIVER=file \
    CACHE_STORE=file
COPY composer.json composer.lock ./
RUN composer install --no-dev --no-interaction --prefer-dist --optimize-autoloader --no-scripts
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements.txt
COPY . .
RUN mkdir -p storage/framework/cache/data storage/framework/sessions storage/framework/views storage/logs bootstrap/cache
RUN composer run-script post-autoload-dump

EXPOSE 8000
CMD ["sh", "-c", "php artisan rayventory:setup && php artisan serve --host=0.0.0.0 --port=8000"]
