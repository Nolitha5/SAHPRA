import json
from pathlib import Path

def test_official_download_queue_is_allowlisted():
    path=Path(__file__).resolve().parents[1]/'regulatory_sources/OFFICIAL_ADDITIONAL_DOWNLOAD_QUEUE.json'
    src=json.loads(path.read_text(encoding='utf-8'))['sources']
    from urllib.parse import urlparse
    hosts={'database.ich.org','www.ema.europa.eu','www.sahpra.org.za'}
    assert len(src)>=7
    assert len({s['source_id'] for s in src}) == len(src)
    assert all(urlparse(s['url']).hostname in hosts and urlparse(s['url']).scheme=='https' for s in src)
    assert 'SAHPRA' in src[0]['source_id']
