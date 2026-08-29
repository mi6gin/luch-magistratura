FROM php:8.3-cli

RUN apt-get update \
    && apt-get install -y --no-install-recommends git unzip libsqlite3-dev python3 python3-pip \
    && docker-php-ext-install pdo_sqlite \
    && rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer
WORKDIR /var/www/html
COPY . .
RUN composer install --no-interaction --prefer-dist
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements.txt

EXPOSE 8000
CMD ["sh", "-c", "composer install --no-interaction --prefer-dist && php artisan serve --host=0.0.0.0 --port=8000"]
