# Деплой ИгроВАН на школа-программирования.рф

> **Технический домен (punycode):** `it-kiber.ru`
> Везде в командах ниже используется punycode-форма — это правильно. В браузере домен отобразится как кириллица автоматически.

# Деплой ИгроВАН на it-kiber.ru

Инструкция для самостоятельного развёртывания на Linux VPS (Ubuntu 22.04+ / Debian 12). Время: 30-60 минут.

**Что в итоге будет работать:**
- `https://it-kiber.ru` — сайт с SSL
- Веб-приложение (Flask + waitress в Docker-контейнере)
- Worker (отдельный контейнер, отправляет родителям видео через 1ч и отчёты через 24ч)
- Wazzup24 интеграция для WhatsApp
- Anthropic Claude для AI-отчётов

**Что нужно перед началом:**
- VPS с SSH-доступом (Beget VPS / Timeweb Cloud / Yandex Cloud / Selectel — любой Linux)
- Доступ к панели регистратора домена kiberone.ru (для A-записи)
- API-ключи: Wazzup24 (из их личного кабинета) и Anthropic (с console.anthropic.com)

---

## Шаг 1. DNS — направить it-kiber.ru на сервер

В панели регистратора домена kiberone.ru (reg.ru / nic.ru / etc.):

1. Открой раздел **Управление DNS**
2. Добавь A-запись:
   - **Имя:** `trial`
   - **Тип:** `A`
   - **Значение:** IP-адрес твоего VPS (узнать: `ip addr show eth0` на сервере или в панели хостинга)
   - **TTL:** 3600 (или дефолт)
3. Сохрани

Проверка с локального компьютера:
```bash
ping it-kiber.ru
```
Должен пинговаться твой IP. DNS обновляется за 5-30 минут.

---

## Шаг 2. Подключиться к серверу

```bash
ssh root@<IP-сервера>
# или с твоим пользователем
ssh user@<IP-сервера>
```

Всё остальное делается на сервере (а не на твоём компьютере).

---

## Шаг 3. Установить Docker (если ещё нет)

Проверь сначала:
```bash
docker --version
```

Если нет — установи (Ubuntu/Debian):
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Перелогинься чтобы группа docker применилась
exit
ssh user@<IP-сервера>
```

Проверь:
```bash
docker run hello-world
```

---

## Шаг 4. Установить nginx + certbot

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

Проверь что nginx работает:
```bash
sudo systemctl status nginx
```

Открой http://<IP-сервера> в браузере — должна быть страница «Welcome to nginx».

---

## Шаг 5. Загрузить код на сервер

Создай папку:
```bash
sudo mkdir -p /opt/igrovan-trial
sudo chown $USER:$USER /opt/igrovan-trial
cd /opt/igrovan-trial
```

**Вариант A — через rsync** (с твоего рабочего компа):
```bash
# С твоего ЛОКАЛЬНОГО компьютера, не на сервере:
rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='.env' \
  C:/Users/Honor/igrovan-trial/ user@<IP-сервера>:/opt/igrovan-trial/
```

**Вариант B — через git** (если запушишь на GitHub/Gitea):
```bash
# На сервере:
git clone https://github.com/<твой-репо>.git /opt/igrovan-trial
```

---

## Шаг 6. Настроить .env

```bash
cd /opt/igrovan-trial
cp deploy/.env.prod.example .env
```

Сгенерируй сильные пароли:
```bash
# ADMIN_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(16))"

# SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Отредактируй `.env`:
```bash
nano .env
```

Заполни обязательно:
- `BASE_URL=https://it-kiber.ru`
- `ADMIN_PASSWORD=<сгенерированный_пароль>`
- `SECRET_KEY=<сгенерированный_ключ>`
- `WAZZUP_API_KEY=<из_личного_кабинета_wazzup24>`
- `WAZZUP_CHANNEL_ID=<из_личного_кабинета_wazzup24>`
- `ANTHROPIC_API_KEY=<с_console.anthropic.com>` (опционально, без него — fallback)

Сохрани (Ctrl+O, Enter, Ctrl+X).

---

## Шаг 7. Запустить приложение в Docker

```bash
cd /opt/igrovan-trial
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

Проверь что оба контейнера живые:
```bash
docker compose -f deploy/docker-compose.prod.yml ps
```

Должно быть `Up` у `igrovan-web` и `igrovan-worker`.

Локальная проверка (без SSL ещё):
```bash
curl -I http://127.0.0.1:8000/admin/login
# должен быть HTTP/1.1 200 OK
```

Если ошибка — смотри логи:
```bash
docker compose -f deploy/docker-compose.prod.yml logs --tail=50 web
docker compose -f deploy/docker-compose.prod.yml logs --tail=50 worker
```

---

## Шаг 8. Настроить nginx для it-kiber.ru

Скопируй конфиг:
```bash
sudo cp /opt/igrovan-trial/deploy/nginx-trial-kiberone.conf /etc/nginx/sites-available/it-kiber.ru
sudo ln -s /etc/nginx/sites-available/it-kiber.ru /etc/nginx/sites-enabled/
sudo nginx -t        # проверка синтаксиса — должно быть "syntax is ok"
sudo systemctl reload nginx
```

Открой `http://it-kiber.ru` в браузере — должна быть страница `/admin/login`.

Если нет — DNS ещё не прогрелся (`ping it-kiber.ru` покажет IP).

---

## Шаг 9. SSL через Let's Encrypt

```bash
sudo certbot --nginx -d it-kiber.ru
```

Certbot:
1. Спросит email → введи свой (для уведомлений об истечении сертификата)
2. Спросит соглашение → A (Agree)
3. Спросит про новости от EFF → N (или Y, как хочешь)
4. Сам перепишет nginx-конфиг, добавит SSL и редирект http→https

Проверь:
```bash
curl -I https://it-kiber.ru/admin/login
# HTTP/2 200
```

Открой в браузере `https://it-kiber.ru/admin` — должна быть страница входа.

Сертификат автообновляется (certbot ставит cron job). Проверить:
```bash
sudo certbot renew --dry-run
```

---

## Шаг 10. Финальная проверка

1. `https://it-kiber.ru/admin/login` — войти с твоим `ADMIN_PASSWORD`
2. «🚀 Начать пробный урок» — создать тестовую сессию
3. Открыть `/parent/<token>` с телефона — проверить что polling работает
4. Загрузить тестовый `.sb3`, выдать паспорт — проверить весь flow

---

## Обновление кода

Когда нужно обновить:
```bash
ssh user@<IP-сервера>
cd /opt/igrovan-trial
./deploy/deploy.sh
```

Скрипт:
- `git pull` (если есть) или напомнит про rsync
- пересоберёт Docker-образ
- перезапустит контейнеры
- почистит старые образы

---

## Полезные команды

```bash
# Логи в реальном времени
docker compose -f deploy/docker-compose.prod.yml logs -f

# Только worker (чтобы видеть отправку WhatsApp)
docker compose -f deploy/docker-compose.prod.yml logs -f worker

# Перезапустить только web
docker compose -f deploy/docker-compose.prod.yml restart web

# Остановить всё
docker compose -f deploy/docker-compose.prod.yml down

# Запустить заново
docker compose -f deploy/docker-compose.prod.yml up -d

# Зайти внутрь контейнера (debug)
docker exec -it igrovan-web /bin/bash
```

---

## Бэкапы

Все данные лежат в `/opt/igrovan-trial/{sessions,games,videos,photos,passports}` — это обычные файлы.

Простой ежедневный бэкап через cron:
```bash
sudo crontab -e
```

Добавь:
```cron
0 3 * * * tar czf /backups/igrovan-$(date +\%F).tar.gz -C /opt/igrovan-trial sessions games videos photos passports
```

(заранее создай `/backups` и подключи внешний диск / S3-копирование)

---

## Что делать если упало

| Проблема | Что проверить |
|---|---|
| 502 Bad Gateway | Контейнеры лежат: `docker compose ... ps`. Перезапусти `up -d` |
| QR не открывает страницу с телефона | DNS / SSL не работают. `curl -I https://it-kiber.ru/` с сервера |
| Wazzup не отправляет | Проверь `.env` ключи + логи worker (`logs -f worker`) |
| Отчёт не генерится | `ANTHROPIC_API_KEY` пуст или невалиден. В fallback отчёт всё равно сгенерится |
| Кончилось место | `df -h`. Видео и фото растут — настрой ротацию или вынеси в S3 |

---

## Готово

После Шага 10 у тебя живой `https://it-kiber.ru`. Можно отдавать наставникам в Челнах. На пробных уроках они логинятся в `/admin`, создают сессии, родители сканируют QR с телефонов.
