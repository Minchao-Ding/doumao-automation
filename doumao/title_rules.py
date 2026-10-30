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


def proposal(old, rule=None):
    """纯函数：依据规则与实际文本提出修改，不依赖任何作品名称或坐标。"""
    spec = rule if rule is not None else DEFAULT_RULE
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

