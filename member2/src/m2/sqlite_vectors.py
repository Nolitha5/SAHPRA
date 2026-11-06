"""Genuine SQLite-persistent vector search as OFFLINE engineering fallback.

Not ChromaDB, not a production vector store, and never a regulatory-validation claim.
Only used for demonstration or compatibility when external dependencies unavailable.
"""
from __future__ import annotations
import sqlite3,json,hashlib
from pathlib import Path
import numpy as np
from .schemas import RegulatoryChunk

class SQLiteVectorStore:
    def __init__(self,embedder,path):
        self.embedder=embedder
        self.collection_name='sqlite-fallback-'+hashlib.sha256(f'{embedder.name}:{embedder.dimension}'.encode()).hexdigest()[:12]
        target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
        self.conn=sqlite3.connect(target)
        self.conn.execute('create table if not exists vectors (collection text, chunk_id text, chunk_json text, embedding_json text, primary key(collection,chunk_id))')
        self.conn.commit()
    def upsert(self,chunks:list[RegulatoryChunk]):
        if not chunks:return
        vecs=self.embedder.embed([c.text for c in chunks])
        if any(len(v)!=self.embedder.dimension for v in vecs):raise ValueError('Vector dimension mismatch')
        self.conn.executemany('insert or replace into vectors values (?,?,?,?)',[
            (self.collection_name,c.chunk_id,c.model_dump_json(),json.dumps(v)) for c,v in zip(chunks,vecs)])
        self.conn.commit()
    def count(self):
        return self.conn.execute('select count(*) from vectors where collection=?',(self.collection_name,)).fetchone()[0]
    def all_chunks(self):
        return [RegulatoryChunk.model_validate_json(r[0]) for r in self.conn.execute(
                'select chunk_json from vectors where collection=? order by chunk_id',(self.collection_name,))]
    def search(self,query,limit):
        if limit<1 or self.count()==0:return []
        q=np.asarray(self.embedder.embed([query],query=True)[0],dtype=float)
        result=[]
        for doc_str,vec_str in self.conn.execute('select chunk_json,embedding_json from vectors where collection=?',(self.collection_name,)):
            doc=RegulatoryChunk.model_validate_json(doc_str)
            vec=np.asarray(json.loads(vec_str),dtype=float)
            score=float(np.dot(q,vec)/max(np.linalg.norm(q)*np.linalg.norm(vec),1e-12))
            result.append((doc,max(0.0,score)))
        return sorted(result,key=lambda pair:(-pair[1],pair[0].chunk_id))[:limit]
    def close(self):self.conn.close()
