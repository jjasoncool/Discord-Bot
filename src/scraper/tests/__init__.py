"""scraper 的單元測試（要在 scraper 容器內跑，bot 容器沒有 curl_cffi 等套件）：

    docker exec -w /app scraper python -m unittest discover -s tests -t . -p 'test_*.py'

scraper 的 logger 直接寫正式的 /logs/scraper*.log，測試期間一律關掉，免得測試觸發的警告混進正式紀錄。
"""
import logging

logging.disable(logging.CRITICAL)
