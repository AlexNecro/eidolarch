from __future__ import annotations
import threading,numpy as np
from . import db
from .ai import embedder
class VectorIndex:
    def __init__(self): self.ids=np.empty((0,),dtype=np.int64);self.matrix=np.empty((0,0),dtype=np.float32);self.meta={};self._lock=threading.Lock();self._key=None;self._count=-1
    def refresh(self,force=False):
        key=(embedder.provider_key,embedder.model_id); rows=db.load_embeddings(*key)
        if not force and key==self._key and len(rows)==self._count:return
        with self._lock:
            self._key=key;self._count=len(rows)
            if not rows:self.ids=np.empty((0,),dtype=np.int64);self.matrix=np.empty((0,0),dtype=np.float32);self.meta={};return
            self.ids=np.array([r['id'] for r in rows],dtype=np.int64); self.matrix=np.vstack([np.frombuffer(r['vector'],dtype=np.float32,count=r['dim']) for r in rows]).astype(np.float32,copy=False); self.meta={int(r['id']):dict(r) for r in rows}
    def search(self,query,limit=80,allowed_ids=None):
        self.refresh();
        if not len(self.ids):return []
        q=embedder.embed_text(query)
        if self.matrix.shape[1]!=q.shape[0]:raise RuntimeError(f'Размер embedding запроса {q.shape[0]} не совпадает с индексом {self.matrix.shape[1]}')
        with self._lock:
            if allowed_ids is None:
                mask=np.ones(len(self.ids),dtype=bool)
            else:
                allowed=set(allowed_ids); mask=np.array([int(x) in allowed for x in self.ids],dtype=bool)
            pos=np.flatnonzero(mask)
            if not len(pos):return []
            scores=self.matrix[pos]@q;k=min(limit,len(scores));local=np.argpartition(scores,-k)[-k:];local=local[np.argsort(scores[local])[::-1]];result=[]
            for j in local:
                i=pos[j];m=dict(self.meta[int(self.ids[i])]);m.pop('vector',None);m['score']=float(scores[j]);result.append(m)
            return result
    def similar_photo(self, photo_id, limit=80):
        self.refresh()
        if not len(self.ids): return []
        row=db.get_embedding(photo_id,embedder.provider_key,embedder.model_id)
        if not row: return []
        q=np.frombuffer(row['vector'],dtype=np.float32,count=row['dim'])
        if self.matrix.shape[1]!=q.shape[0]: return []
        with self._lock:
            scores=self.matrix@q
            valid=np.flatnonzero(self.ids!=int(photo_id))
            if not len(valid): return []
            k=min(limit,len(valid)); vals=scores[valid]
            local=np.argpartition(vals,-k)[-k:]; local=local[np.argsort(vals[local])[::-1]]
            result=[]
            for j in local:
                i=valid[j]; m=dict(self.meta[int(self.ids[i])]); m.pop('vector',None); m['score']=float(scores[i]); result.append(m)
            return result
vector_index=VectorIndex()
