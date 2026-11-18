"""Compare rooted MIR declaration graphs up to identifier renaming and spans."""
import json
from pathlib import Path
import re


class Identity:
    def __init__(self, old, new):
        self.modules=[json.loads(Path(p).read_text()) for p in (old,new)]
        if self.modules[0]['version'] != self.modules[1]['version']:
            raise ValueError('Different MIR schema versions')
        self.indices=[]
        for module in self.modules:
            index={}
            for section in ['fns','tys','adts','statics','intrinsics','vtables','traits']:
                for node in module[section]:
                    entries=index.setdefault(node['name'],{})
                    if section in entries:
                        raise ValueError('Duplicate MIR declaration: '+node['name'])
                    entries[section]=node
            self.indices.append(index)
        self.forward={}
        self.reverse={}
        self.queue=[]
        self.seen=set()
        self.positions=0
        self.language_items=[{v['name']:v['orig_def_id'] for v in module['lang_items']} for module in self.modules]
        self.used_language_items=set()
        for name in self.language_items[0].keys() & self.language_items[1].keys():
            if self.language_items[0][name] != self.language_items[1][name]:
                raise ValueError('Different language-item binding: '+name)

    def bind(self, old, new, path):
        if old in self.forward and self.forward[old]!=new:
            raise ValueError(f'Inconsistent identifier mapping at {path}: {old} -> {new}')
        if new in self.reverse and self.reverse[new]!=old:
            raise ValueError(f'Noninjective identifier mapping at {path}: {old} -> {new}')
        self.forward[old]=new
        self.reverse[new]=old
        if (old,new) not in self.seen:
            self.seen.add((old,new))
            self.queue.append((old,new))

    def compare(self, old, new, path):
        if type(old)!=type(new):
            raise ValueError(f'Different node types at {path}')
        if isinstance(old,dict):
            if set(old)-{'pos'}!=set(new)-{'pos'}:
                raise ValueError(f'Different fields at {path}')
            for key in old:
                if key=='pos':
                    self.positions+=1
                else:
                    self.compare(old[key],new[key],path+'/'+key)
        elif isinstance(old,list):
            if len(old)!=len(new):
                raise ValueError(f'Different list lengths at {path}: {len(old)}, {len(new)}')
            for i,(left,right) in enumerate(zip(old,new)):
                self.compare(left,right,path+'/'+str(i))
        elif isinstance(old,str):
            for name in self.language_items[0].keys() | self.language_items[1].keys():
                if old == name or old.startswith(name+'::') or new == name or new.startswith(name+'::'):
                    if name not in self.language_items[0] or name not in self.language_items[1]:
                        raise ValueError('Missing used language-item binding: '+name)
                    self.used_language_items.add(name)
            old_id,new_id=old in self.indices[0],new in self.indices[1]
            if old_id or new_id:
                if not old_id or not new_id:
                    raise ValueError(f'Identifier/declaration mismatch at {path}: {old}, {new}')
                self.bind(old,new,path)
            elif old!=new:
                # Uninstantiated nominal identifiers must retain their exact
                # Rust path; only the crate disambiguator may differ.
                nominal=lambda s: re.sub(r'(?<=/)[0-9a-f]+(?=::)','<crate>',s)
                if (path.rsplit('/',1)[-1] not in {'name','def_id','orig_def_id'} or
                        '::' not in old or nominal(old)!=nominal(new)):
                    raise ValueError(f'Different value at {path}: {old!r} vs {new!r}')
        elif old!=new:
            raise ValueError(f'Different literal at {path}: {old!r} vs {new!r}')

    def rooted(self, functions):
        for old,new in functions:
            self.bind(old,new,'root')
        while self.queue:
            old,new=self.queue.pop()
            left,right=self.indices[0][old],self.indices[1][new]
            if set(left)!=set(right):
                raise ValueError(f'Different declaration kinds: {old}: {set(left)} / {new}: {set(right)}')
            self.compare(left,right,old)
        return {'status':'matched','declarations':len(self.seen),'ignored_source_positions':self.positions,
                'used_language_items':sorted(self.used_language_items)}
