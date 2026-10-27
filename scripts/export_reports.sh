#!/bin/sh
# Выполняет запросы витрин и сохраняет первые строки результата в csv:
#   last_paid_click.sql           -> last_paid_click.csv (топ-10)
#   aggregate_last_paid_click.sql -> aggregate_last_paid_click.csv (топ-15)
# Сортировка задана в самих запросах, здесь берутся первые N строк.
# Время записывается как в выгрузке DBeaver из шага 2:
# «ГГГГ-ММ-ДД чч:мм:сс.ммм» (миллисекунды, без микросекунд).
# Запускается внутри контейнера db: make reports
set -eu

PROJECT_DIR="${PROJECT_DIR:-/project}"

export_report() {
    name="$1"
    rows="$2"
    psql -X -q -v ON_ERROR_STOP=1 --csv \
        -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -f "$PROJECT_DIR/$name.sql" \
        | head -n "$((rows + 1))" \
        | awk '{
            rest = $0
            out = ""
            while (match(rest, /[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9](\.[0-9]+)?/)) {
                stamp = substr(rest, RSTART, RLENGTH)
                millis = substr(substr(stamp, 21) "000", 1, 3)
                out = out substr(rest, 1, RSTART - 1) substr(stamp, 1, 19) "." millis
                rest = substr(rest, RSTART + RLENGTH)
            }
            print out rest
        }' > "$PROJECT_DIR/$name.csv"
    echo "$name.csv: $(($(wc -l < "$PROJECT_DIR/$name.csv") - 1)) строк"
}

export_report last_paid_click 10
export_report aggregate_last_paid_click 15
