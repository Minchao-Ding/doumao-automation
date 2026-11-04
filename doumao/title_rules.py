"""Pure title-transformation rules; no GUI automation dependencies."""
from __future__ import annotations
import json
from pathlib import Path

DEFAULT_RULE = {
    'folder': '饮品',
    'rule_type': 'replace_unique_separator',
    'old_separator': ' ',
    'new_separator': '｜',
    'forbid_existing': ['｜'],
    'max_length': 64,
}


def load_rule(path=None):
    """可配置的标题转换规则；文件不列举任何具体作品名。"""
    spec = dict(DEFAULT_RULE)
    if path:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('规则配置必须是 JSON 对象。')
        spec.update(data)
    if spec.get('rule_type') != 'replace_unique_separator':
        raise ValueError('当前支持的规则类型仅 replace_unique_separator。')
    old, replacement = spec.get('old_separator'), spec.get('new_separator')
    if not isinstance(old,str) or not (1 <= len(old) <= 8):
        raise ValueError('old_separator 必须为 1–8 个字符。')
    if not isinstance(replacement,str) or not (1 <= len(replacement) <= 8):
        raise ValueError('new_separator 必须为 1–8 个字符。')
    if old == replacement:
        raise ValueError('新旧分隔符相同，拒绝无意义修改。')
    forbidden = spec.get('forbid_existing',[])
    if not isinstance(forbidden,list) or not all(isinstance(v,str) and v for v in forbidden):
        raise ValueError('forbid_existing 必须为非空字符串数组。')
    max_length = spec.get('max_length')
    if not isinstance(max_length,int) or not 4 <= max_length <= 128:
        raise ValueError('max_length 必须为 4–128。')
    if not isinstance(spec.get('folder'),str) or not spec['folder']:
        raise ValueError('folder 必须填写目标文件夹名称。')
    return spec


def transform_text(title: str, rule: dict) -> str | None:
    """Reusable text-only operations; exact user data lives in CLI arguments.

    No character/IP/collection names are built into this module.  For search
    queue mode, the postcondition guards search-result removal before saving.
    """
    if not isinstance(title, str) or not title or any(c in title for c in ('\r','\n','\x00')):
        raise ValueError('Invalid original title')
    kind = rule.get('rule_type')
    if kind == 'remove_prefix':
        prefix = rule.get('prefix')
        if not isinstance(prefix, str) or not prefix:
            raise ValueError('A nonempty exact prefix is required')
        if not title.startswith(prefix):
            return None
        updated = title[len(prefix):]
    elif kind == 'replace_text':
        source, target = rule.get('old'), rule.get('new')
        if not isinstance(source, str) or not source or not isinstance(target, str) or source == target:
            raise ValueError('A nonempty old string and different replacement are required')
        if source not in title:
            return None
        updated = title.replace(source, target)
    elif kind == 'append_suffix':
        suffix = rule.get('suffix')
        delimiter = rule.get('delimiter', '｜')
        forbidden = rule.get('forbid_other', [])
        if not isinstance(suffix, str) or not suffix or not isinstance(delimiter, str):
            raise ValueError('Invalid suffix or delimiter')
        if not isinstance(forbidden, list) or not all(isinstance(s, str) for s in forbidden):
            raise ValueError('Invalid conflict list')
        if suffix in title or any(s and s in title for s in forbidden):
            return None
        updated = title + delimiter + suffix
    else:
        raise ValueError(f'Unsupported title rule: {kind!r}')

    if not updated or not updated.strip() or any(c in updated for c in ('\r','\n','\x00')):
        raise ValueError('Refusing invalid transformed title')
    if len(updated) > rule.get('max_length', 64):
        raise ValueError('Transformed title exceeds supported editor length')
    # Only the search-result queue requires that the edited card disappears.
    search_term = rule.get('search_must_disappear')
    if search_term is not None:
        if not isinstance(search_term, str) or not search_term or search_term not in title:
            raise ValueError('The actual original title does not contain the expected search text')
        if search_term in updated:
            raise ValueError('The replacement still matches the search; queue mode is unsafe')
    return updated


def proposal(old, rule=None):
    """纯函数：依据规则与实际文本提出修改，不依赖任何作品名称或坐标。"""
    spec = rule if rule is not None else DEFAULT_RULE
    if spec.get('rule_type') != 'replace_unique_separator':
        return transform_text(old, spec)
    if not old or old != old.strip() or len(old) > spec['max_length']:
        return None
    if any(c in old for c in ('\n','\r','\t','\u3000')):
        return None
    if any(c in old for c in spec['forbid_existing']):
        return None
    delim = spec['old_separator']
    if old.count(delim) != 1:
        return None
    left,right = old.split(delim,1)
    if not left or not right:
        return None
    transformed = left + spec['new_separator'] + right
    if transformed == old or len(transformed) > spec['max_length']:
        return None
    return transformed

