"""Research-only source-archive inventory and search, isolated from regulatory evidence.

User-supplied secondary compendium exports are NEVER auto-promoted to the approved RKB.
The mirror is not an authorised publisher assertion. No autonomous regulatory verdicts.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zipfile
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

ARCHIVE_SPECS = {
    'formulated-general [webofpharma.com].zip': ('BP_HTML', 'FORMULATED_GENERAL'),
    'general-notices [webofpharma.com].zip': ('BP_HTML', 'GENERAL_NOTICES'),
    'general-notices [webofpharma.com](1).zip': ('BP_HTML', 'GENERAL_NOTICES'),
    'prelims [webofpharma.com].zip': ('BP_HTML', 'PRELIMINARY'),
    'herbal-drugs [webofpharma.com].zip': ('BP_HTML', 'HERBAL_DRUG'),
    'New folder (4).zip': ('BP_HTML', 'FORMULATED_PRODUCT'),
    'New folder (5).zip': ('BP_HTML', 'FORMULATED_PRODUCT'),
    'New folder (2)(1).zip': ('BP_HTML', 'SUBSTANCE_MONOGRAPH'),
    'New folder (7).zip': ('BP_HTML', 'SUBSTANCE_MONOGRAPH'),
    'New folder (8).zip': ('BP_HTML', 'SUBSTANCE_MONOGRAPH'),
    'New folder (9).zip': ('PH_EUR_EXTRACT', 'GENERAL_METHOD_OR_MONOGRAPH'),
    'New folder (10).zip': ('PH_EUR_EXTRACT', 'SUBSTANCE_MONOGRAPH'),
    'New folder (11).zip': ('PH_EUR_EXTRACT', 'SUBSTANCE_MONOGRAPH'),
    'General.zip': ('MIXED_GENERAL', 'GENERAL_METHOD'),
}
REVIEW_STATUS = 'QUARANTINED_UNVERIFIED_EDITION_RIGHTS_AND_APPLICABILITY'
MAX_ENTRY = 16 * 1024 * 1024  # cap each PDF/HTML; never execute embedded scripts
MAX_RATIO = 180  # reject zip bomb ratios


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_entry(info: zipfile.ZipInfo) -> bool:
    p = PurePosixPath(info.filename)
    if info.is_dir() or p.is_absolute() or '..' in p.parts or '\\' in info.filename:
        return False
    if info.file_size <= 0 or info.file_size > MAX_ENTRY:
        return False
    if (info.file_size / max(1, info.compress_size)) > MAX_RATIO:
        return False
    if (info.external_attr >> 16) & 0o170000 == 0o120000:  # symbolic links
        return False
    return p.suffix.lower() in ('.html', '.pdf')


def clean_html(data: bytes) -> tuple[str, str]:
    try:
        from lxml import html as lxml_html
        tree = lxml_html.fromstring(data)
        title = ' '.join(tree.xpath('//title/text()'))[:250]
        for node in tree.xpath('//script|//style|//noscript|//footer|//nav'):
            node.drop_tree()
        main = tree.xpath('//article') or tree.xpath('//main') or [tree]
        body = ' '.join(main[0].itertext())
    except Exception:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(data, 'html.parser')
        title = soup.title.get_text(' ', strip=True) if soup.title else ''
        for node in soup(['script','style','noscript','footer','nav']): node.decompose()
        body = (soup.find('article') or soup.find('main') or soup).get_text(' ', strip=True)
    return re.sub(r'\s+', ' ', title).strip(), re.sub(r'\s+', ' ', body).strip()


def pages_from_pdf(data: bytes) -> Iterable[tuple[int, str]]:
    import fitz
    with fitz.open(stream=data, filetype='pdf') as doc:
        if doc.page_count > 160:
            return
        for index, page in enumerate(doc, start=1):
            value = re.sub(r'\s+', ' ', page.get_text(sort=True)).strip()
            if len(value) >= 30:
                yield index, value


def detect_edition(source_group: str, text: str) -> str:
    t = text[:3000]
    if source_group == 'PH_EUR_EXTRACT':
        m = re.search(r'EUROPEAN\s+PHARMACOPOEIA\s+(\d+(?:\.\d+)?)', t, re.I)
        return ('Ph. Eur. ' + m.group(1)) if m else 'Ph. Eur. edition unverified'
    if source_group == 'BP_HTML':
        m = re.search(r'BP\s+(20\d{2})(?:\s*\([^)]{0,70}\))?',t,re.I)
        return m.group(0)[:85] if m else 'BP edition unverified'
    return 'Edition unverified'


def init_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.execute('PRAGMA journal_mode=WAL')
    con.executescript('''
      CREATE TABLE IF NOT EXISTS archive_sources (
        archive_name TEXT PRIMARY KEY, sha256 TEXT, size_bytes INTEGER,
        source_family TEXT, topic TEXT, total_entries INTEGER, eligible_entries INTEGER,
        invalid_entries INTEGER, state TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS documents (
        doc_id TEXT PRIMARY KEY, archive_name TEXT NOT NULL, path_in_archive TEXT NOT NULL,
        title TEXT NOT NULL, source_family TEXT, topic TEXT, edition_claim TEXT,
        content_sha256 TEXT, number_of_pages INTEGER, review_status TEXT NOT NULL,
        source_url TEXT, licence_verified INTEGER NOT NULL DEFAULT 0,
        applicability_verified INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(archive_name) REFERENCES archive_sources(archive_name)
      );
      CREATE TABLE IF NOT EXISTS passages (
        passage_id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, source_page INTEGER,
        content TEXT NOT NULL, FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
      );
      CREATE VIRTUAL TABLE IF NOT EXISTS passage_search USING fts5(
        passage_id UNINDEXED, title, content, tokenize='unicode61'
      );
      CREATE INDEX IF NOT EXISTS doc_archive ON documents(archive_name);
      CREATE INDEX IF NOT EXISTS passage_doc ON passages(doc_id);
    ''')
    return con


def inventory_archives(archive_dir: Path, *, names: list[str] | None = None) -> list[dict]:
    rows = []
    selected = names or list(ARCHIVE_SPECS)
    for filename in selected:
        source_family, topic = ARCHIVE_SPECS[filename]
        path = archive_dir / filename
        if not path.exists():
            rows.append({'archive_name':filename,'present':False,'source_family':source_family,'topic':topic})
            continue
        with zipfile.ZipFile(path) as z:
            infos = [x for x in z.infolist() if not x.is_dir()]
            valid = [x for x in infos if safe_entry(x)]
            row = {'archive_name':filename,'present':True, 'source_family':source_family,'topic':topic,
                   'file_size_bytes':path.stat().st_size, 'sha256':sha_file(path),
                   'total_entries':len(infos),'eligible_entries':len(valid),
                   'invalid_entries':len(infos)-len(valid),
                   'format_counts':{ext:sum(1 for x in valid if x.filename.lower().endswith(ext)) for ext in ('.pdf','.html')},
                   'review_status':REVIEW_STATUS}
            rows.append(row)
    return rows


def build_discovery(archive_dir: Path, output_db: Path, *, selected: list[str] | None = None,
                    skip_existing: bool = True, max_documents: int | None = None) -> dict:
    """Build an isolated full-text *discovery* index; never regulatory evidence.

    No external URLs fetched, scripts executed, or source archives changed. Entry size capped.
    """
    con = init_db(output_db)
    done = errors = duplicates = 0
    seen_content = {x[0] for x in con.execute('SELECT content_sha256 FROM documents')}
    entries_done = []
    report_rows = inventory_archives(archive_dir, names=selected)
    for row in report_rows:
        if not row['present']: continue
        name = row['archive_name']
        con.execute('INSERT OR REPLACE INTO archive_sources VALUES (?,?,?,?,?,?,?, ?, ?)',
                    (name,row['sha256'],row['file_size_bytes'],row['source_family'],row['topic'],
                     row['total_entries'],row['eligible_entries'],row['invalid_entries'],REVIEW_STATUS))
        with zipfile.ZipFile(archive_dir/name) as z:
            for info in z.infolist():
                if not safe_entry(info):continue
                doc_id=hashlib.sha256((name+'\0'+info.filename).encode('utf-8')).hexdigest()[:24]
                if skip_existing and con.execute('SELECT 1 FROM documents WHERE doc_id=?',(doc_id,)).fetchone():continue
                if max_documents is not None and done >= max_documents:break
                try:
                    content=z.read(info)
                    digest=hashlib.sha256(content).hexdigest()
                    if digest in seen_content:
                        duplicates+=1;continue
                    if info.filename.lower().endswith('.html'):
                        title, body=clean_html(content)
                        title=title or Path(info.filename).stem
                        passages=[(None,body)] if len(body)>=30 else []
                    else:
                        title=Path(info.filename).stem
                        passages=list(pages_from_pdf(content))
                        passages=[(page,body) for page,body in passages]
                    if not passages: errors+=1;continue
                    observed = detect_edition(row['source_family'], passages[0][1])
                    con.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                               (doc_id,name,info.filename,title,row['source_family'],row['topic'],observed,digest,
                                len(passages) if info.filename.lower().endswith('.pdf') else None,REVIEW_STATUS,None,0,0))
                    for page, body in passages:
                        p_id=hashlib.sha256(f'{doc_id}:{page}'.encode()).hexdigest()[:30]
                        con.execute('INSERT INTO passages VALUES(?,?,?,?)', (p_id,doc_id,page,body))
                        con.execute('INSERT INTO passage_search(passage_id,title,content) VALUES(?,?,?)', (p_id,title,body))
                    seen_content.add(digest)
                    done+=1
                    if done%100==0:con.commit()
                except Exception:
                    errors+=1
        con.commit()
        entries_done.append({'archive':name,'new_documents':done,'errors_cumulative':errors})
        if max_documents is not None and done>=max_documents:break
    counts={'documents':con.execute('SELECT COUNT(*) FROM documents').fetchone()[0],
            'passages':con.execute('SELECT COUNT(*) FROM passages').fetchone()[0],
            'archives':con.execute('SELECT COUNT(*) FROM archive_sources').fetchone()[0]}
    con.close()
    return {'created_at_utc':datetime.now(timezone.utc).isoformat(),'index':str(output_db),
            'status':'UNVERIFIED_RESEARCH_DISCOVERY_ONLY_NOT_REGULATORY_EVIDENCE',
            'new_documents':done,'duplicate_file_entries_skipped':duplicates,'extraction_errors':errors,
            'counts':counts,'archive_inventory':report_rows,'archive_progress':entries_done,
            'regulatory_approval':False,'expert_validated':False,'training_performed':False}


def search_unverified(db: Path, query: str, *, limit: int = 5, source_family: str | None = None,
                      include_unreviewed: bool = False, topic: str | None = None, exact_title: bool = False) -> dict:
    """Explicit opt-in is required to *view* non-authoritative discovery snippets."""
    if not include_unreviewed:
        return {'status':'REVIEW_REQUIRED', 'hits':[], 'regulatory_evidence':False,
                'message':'This index holds unverified compendial extracts; opt in for research-only discovery.'}
    terms = re.findall(r'[\w-]{2,}', query, flags=re.UNICODE)[:10]
    if not terms:
        return {'status':'EMPTY_QUERY','hits':[],'regulatory_evidence':False}
    match=' OR '.join('"'+x.replace('"','')+'"' for x in terms)
    con=sqlite3.connect(str(db))
    sql='''SELECT d.title,d.source_family,d.topic,d.edition_claim,d.archive_name,d.path_in_archive,
                  p.source_page, substr(p.content,1,420),bm25(passage_search),d.review_status
             FROM passage_search JOIN passages p ON passage_search.passage_id=p.passage_id
                  JOIN documents d ON d.doc_id=p.doc_id WHERE passage_search MATCH ?'''
    params=[match]
    if source_family:sql+=' AND d.source_family=?';params.append(source_family)
    if topic:sql+=' AND d.topic=?';params.append(topic)
    sql+=' ORDER BY bm25(passage_search) LIMIT ?';params.append(200 if exact_title else min(50,max(1,limit)))
    rows=con.execute(sql,params).fetchall();con.close()
    if exact_title:
        def normalized(value):return re.sub(r'[^a-z0-9]+',' ',value.casefold()).strip()
        needle=normalized(query)
        rows=[row for row in rows if normalized(row[0].split(' - British Pharmacopoeia')[0])==needle]
    rows=rows[:min(50,max(1,limit))]
    keys=['title','source_family','topic','edition_claim','archive_name','path_in_archive','source_page','preview_text','rank_score','review_status']
    return {'status':'UNVERIFIED_RESEARCH_MATCH' if rows else 'NO_MATCH', 'query':query,
            'regulatory_evidence':False,'requires_human_review':True,
            'warning':'Do not use for approval, regulatory compliance conclusions, or clinical decisions.',
            'hits':[dict(zip(keys,x)) for x in rows]}
