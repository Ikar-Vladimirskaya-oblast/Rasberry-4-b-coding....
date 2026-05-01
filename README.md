# ИКАР RFID Organizer

Запуск backend на Raspberry Pi:

```bash
cd /home/alex/organizer_app
sudo PYTHONPATH=/home/alex/.local/lib/python3.13/site-packages ./run.sh
```

Веб-панель:

```text
http://192.168.3.17:5000
```

Открыть как приложение на экране Raspberry:

```bash
/home/alex/organizer_app/launch_app.sh
```

Hardware:

- TCA9548A: `0x70`
- PN532: `0x24`
- ридеры: каналы `3, 4, 5, 6`
- LED: GPIO18, 4 WS2812
- маппинг: `3 -> LED4`, `4 -> LED3`, `5 -> LED2`, `6 -> LED1`
