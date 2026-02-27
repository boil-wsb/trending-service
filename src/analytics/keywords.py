"""
关键词提取模块
使用 jieba 进行中文分词和关键词提取
"""

import jieba
import jieba.analyse
from collections import Counter
from typing import List, Dict, Set, TYPE_CHECKING
import re

if TYPE_CHECKING:
    from src.fetchers import TrendingItem


class KeywordExtractor:
    """关键词提取器"""
    
    # 停用词集合 - 扩展版本
    STOP_WORDS: Set[str] = {
        # 中文常用停用词
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也',
        '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这', '那',
        '这些', '那些', '这个', '那个', '之', '与', '及', '等', '或', '但', '而', '如果', '因为',
        '所以', '可以', '可能', '需要', '进行', '通过', '对于', '关于', '作为', '成为', '使用',
        '基于', '实现', '支持', '提供', '包括', '包含', '涉及', '相关', '主要', '重要', '最新',
        '第一', '如何', '什么', '为什么', '怎么', '怎样', '介绍', '分享', '讨论', '我们', '你们',
        '他们', '它们', '这里', '那里', '哪里', '时候', '现在', '今天', '明天', '昨天', '已经',
        '正在', '开始', '结束', '完成', '得到', '做出', '提出', '发现', '认为', '表示', '觉得',
        
        # HackerNews 特有停用词
        'hn', 'show', 'ask', 'tell', 'launch', 'project', 'built', 'made', 'created',
        'using', 'used', 'use', 'new', 'way', 'make', 'get', 'like', 'just', 'now',
        'time', 'year', 'years', 'day', 'days', 'week', 'month', 'work', 'works',
        'web', 'site', 'website', 'online', 'app', 'application', 'tool', 'tools',
        'system', 'service', 'platform', 'feature', 'features', 'update', 'version',
        'release', 'released', 'launch', 'launched', 'announced', 'available',
        'free', 'open', 'source', 'github', 'code', 'repo', 'repository',
        'write', 'writing', 'written', 'wrote', 'article', 'post', 'blog',
        'read', 'reading', 'book', 'books', 'paper', 'papers', 'documentation',
        'learn', 'learning', 'learned', 'tutorial', 'guide', 'course', 'courses',
        
        # 常见无意义词汇
        'vs', 'via', 'per', 'one', 'two', 'three', 'first', 'second', 'last',
        'next', 'previous', 'back', 'forward', 'up', 'down', 'left', 'right',
        'more', 'less', 'most', 'least', 'many', 'much', 'some', 'any', 'all',
        'each', 'every', 'both', 'either', 'neither', 'other', 'another',
        'same', 'different', 'such', 'only', 'even', 'also', 'still', 'yet',
        'already', 'always', 'never', 'sometimes', 'often', 'usually',
        
        # 技术通用停用词
        'api', 'http', 'https', 'www', 'com', 'org', 'net', 'io', 'html', 'css',
        'js', 'javascript', 'python', 'java', 'go', 'rust', 'cpp', 'c++', 'ruby',
        'php', 'swift', 'kotlin', 'scala', 'r', 'matlab', 'sql', 'nosql',
        'web', 'mobile', 'desktop', 'server', 'client', 'frontend', 'backend',
        'database', 'db', 'cache', 'cloud', 'aws', 'azure', 'gcp', 'docker',
        'kubernetes', 'k8s', 'container', 'containers', 'microservice',
        'architecture', 'framework', 'library', 'libraries', 'package', 'module',
        'component', 'components', 'function', 'functions', 'method', 'methods',
        'class', 'classes', 'object', 'objects', 'variable', 'variables',
        'data', 'type', 'types', 'string', 'strings', 'number', 'numbers',
        'array', 'arrays', 'list', 'lists', 'map', 'maps', 'set', 'sets',
        'key', 'keys', 'value', 'values', 'item', 'items', 'element', 'elements',
        'user', 'users', 'admin', 'root', 'default', 'test', 'testing',
        'dev', 'development', 'prod', 'production', 'staging', 'local',
        'build', 'building', 'built', 'deploy', 'deployment', 'deployed',
        'run', 'running', 'start', 'starting', 'started', 'stop', 'stopping',
        'stopped', 'install', 'installation', 'installed', 'setup', 'set',
        'configure', 'configuration', 'configured', 'setting', 'settings',
        'option', 'options', 'param', 'params', 'parameter', 'parameters',
        'arg', 'args', 'argument', 'arguments', 'flag', 'flags',
        'enable', 'enabled', 'disable', 'disabled', 'active', 'inactive',
        'true', 'false', 'yes', 'no', 'on', 'off', 'null', 'none', 'nil',
        'error', 'errors', 'exception', 'exceptions', 'bug', 'bugs', 'fix',
        'fixed', 'issue', 'issues', 'problem', 'problems', 'solution', 'solutions',
        'support', 'supported', 'unsupported', 'compatible', 'compatibility',
        'performance', 'optimization', 'optimize', 'optimized', 'speed', 'fast',
        'slow', 'memory', 'cpu', 'gpu', 'disk', 'storage', 'network', 'bandwidth',
        'security', 'secure', 'insecure', 'safe', 'unsafe', 'privacy', 'private',
        'public', 'protected', 'internal', 'external', 'import', 'export',
        'input', 'output', 'in', 'out', 'read', 'write', 'open', 'close',
        'create', 'created', 'creation', 'delete', 'deleted', 'deletion',
        'remove', 'removed', 'removal', 'add', 'added', 'addition', 'update',
        'updated', 'updating', 'upgrade', 'upgraded', 'downgrade', 'downgraded',
        'change', 'changed', 'changing', 'modify', 'modified', 'modification',
        'edit', 'edited', 'editing', 'save', 'saved', 'saving', 'load', 'loaded',
        'loading', 'import', 'imported', 'importing', 'export', 'exported',
        'exporting', 'parse', 'parsed', 'parsing', 'serialize', 'serialized',
        'serialization', 'deserialize', 'deserialized', 'deserialization',
        'encode', 'encoded', 'encoding', 'decode', 'decoded', 'decoding',
        'encrypt', 'encrypted', 'encryption', 'decrypt', 'decrypted', 'decryption',
        'compress', 'compressed', 'compression', 'decompress', 'decompressed',
        'decompression', 'zip', 'unzip', 'gzip', 'tar', 'rar', '7z',
        'format', 'formats', 'convert', 'converted', 'conversion', 'transform',
        'transformed', 'transformation', 'translate', 'translated', 'translation',
        'generate', 'generated', 'generation', 'create', 'created', 'creation',
        'make', 'made', 'produce', 'produced', 'production', 'render', 'rendered',
        'rendering', 'draw', 'drawn', 'drawing', 'paint', 'painted', 'painting',
        'display', 'displayed', 'displaying', 'show', 'showed', 'shown', 'showing',
        'hide', 'hidden', 'hiding', 'visible', 'invisible', 'appear', 'appeared',
        'appearing', 'disappear', 'disappeared', 'disappearing', 'view', 'viewed',
        'viewing', 'watch', 'watched', 'watching', 'see', 'seen', 'seeing',
        'look', 'looked', 'looking', 'find', 'found', 'finding', 'search',
        'searched', 'searching', 'query', 'queried', 'querying', 'filter',
        'filtered', 'filtering', 'sort', 'sorted', 'sorting', 'order', 'ordered',
        'ordering', 'rank', 'ranked', 'ranking', 'rate', 'rated', 'rating',
        'score', 'scored', 'scoring', 'point', 'points', 'count', 'counted',
        'counting', 'number', 'numbers', 'total', 'sum', 'average', 'mean',
        'median', 'mode', 'min', 'max', 'minimum', 'maximum', 'limit', 'limited',
        'limiting', 'offset', 'page', 'pages', 'pagination', 'cursor', 'cursors',
        'index', 'indexes', 'indices', 'key', 'keys', 'primary', 'foreign',
        'unique', 'duplicate', 'duplicates', 'copy', 'copied', 'copying',
        'clone', 'cloned', 'cloning', 'fork', 'forked', 'forking', 'branch',
        'branches', 'branched', 'branching', 'merge', 'merged', 'merging',
        'commit', 'commits', 'committed', 'committing', 'push', 'pushed',
        'pushing', 'pull', 'pulled', 'pulling', 'fetch', 'fetched', 'fetching',
        'clone', 'cloned', 'cloning', 'checkout', 'checked', 'checking',
        'status', 'log', 'logs', 'history', 'diff', 'diffs', 'patch', 'patches',
        'blame', 'annotate', 'tag', 'tags', 'tagged', 'tagging', 'release',
        'releases', 'released', 'releasing', 'version', 'versions', 'v',
        'alpha', 'beta', 'rc', 'stable', 'latest', 'nightly', 'snapshot',
        'draft', 'prerelease', 'pre-release', 'deprecated', 'obsolete',
        'legacy', 'modern', 'current', 'old', 'new', 'initial', 'final',
    }
    
    # 技术领域专业词汇（保留这些词）
    TECH_TERMS: Set[str] = {
        'ai', 'artificial', 'intelligence', 'machine', 'learning', 'ml',
        'deep', 'neural', 'network', 'networks', 'nlp', 'cv', 'vision',
        'llm', 'llms', 'gpt', 'chatgpt', 'claude', 'gemini', 'llama',
        'transformer', 'transformers', 'bert', 'gpt2', 'gpt3', 'gpt4',
        'diffusion', 'stable', 'midjourney', 'dalle', 'dall-e',
        'tensorflow', 'pytorch', 'keras', 'jax', 'onnx', 'huggingface',
        'langchain', 'llamaindex', 'openai', 'anthropic', 'cohere',
        'vector', 'embedding', 'embeddings', 'rag', 'agent', 'agents',
        'prompt', 'prompts', 'prompting', 'fine-tune', 'finetune',
        'training', 'inference', 'model', 'models', 'dataset', 'datasets',
        'benchmark', 'benchmarks', 'evaluation', 'metric', 'metrics',
    }
    
    def __init__(self, top_k: int = 10, allow_pos: tuple = ('ns', 'n', 'vn', 'v', 'nr', 'nz', 'eng')):
        """
        初始化关键词提取器
        
        Args:
            top_k: 提取关键词数量
            allow_pos: 允许的词性（地名、名词、动名词、动词、人名、专有名词、英文）
        """
        self.top_k = top_k
        self.allow_pos = allow_pos
    
    def _preprocess_text(self, text: str) -> str:
        """预处理文本"""
        if not text:
            return ""
        
        # 移除 URL
        text = re.sub(r'https?://\S+', '', text)
        
        # 移除特殊字符，但保留中英文
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', text)
        
        # 移除多余空格
        text = ' '.join(text.split())
        
        return text.lower()
    
    def extract(self, text: str) -> List[str]:
        """
        从文本中提取关键词
        
        Args:
            text: 输入文本
            
        Returns:
            List[str]: 关键词列表
        """
        if not text or not isinstance(text, str):
            return []
        
        # 预处理文本
        text = self._preprocess_text(text)
        
        if not text:
            return []
        
        # 使用 TF-IDF 算法提取关键词
        keywords = jieba.analyse.extract_tags(
            text,
            topK=self.top_k * 2,  # 提取更多，然后过滤
            withWeight=False,
            allowPOS=self.allow_pos
        )
        
        # 过滤停用词和短词
        filtered = []
        for kw in keywords:
            kw_lower = kw.lower()
            
            # 跳过停用词
            if kw_lower in self.STOP_WORDS:
                continue
            
            # 跳过纯数字
            if kw.isdigit():
                continue
            
            # 跳过长度过短的词（英文至少3个字符，中文至少2个）
            if len(kw) < 2:
                continue
            
            # 检查是否包含太多停用词
            words = kw_lower.split()
            if len(words) > 1:
                # 如果是多词组合，检查是否主要由停用词组成
                stop_word_count = sum(1 for w in words if w in self.STOP_WORDS)
                if stop_word_count / len(words) > 0.5:
                    continue
            
            filtered.append(kw)
            
            # 达到目标数量就停止
            if len(filtered) >= self.top_k:
                break
        
        return filtered
    
    def extract_from_item(self, item) -> List[str]:
        """
        从 TrendingItem 中提取关键词
        
        Args:
            item: 热点数据项
            
        Returns:
            List[str]: 关键词列表
        """
        # 组合标题和描述
        text = item.title
        if item.description and item.description != '-':
            text += ' ' + item.description
        
        return self.extract(text)
    
    def extract_from_items(self, items: List) -> Dict[str, int]:
        """
        从多个数据项中提取并统计关键词
        
        Args:
            items: 热点数据列表
            
        Returns:
            Dict[str, int]: 关键词及其出现次数
        """
        all_keywords = []
        
        for item in items:
            keywords = self.extract_from_item(item)
            all_keywords.extend(keywords)
        
        # 统计词频
        counter = Counter(all_keywords)
        return dict(counter.most_common(50))
    
    def extract_by_source(self, items: List) -> Dict[str, Dict[str, int]]:
        """
        按数据源分组提取关键词
        
        Args:
            items: 热点数据列表
            
        Returns:
            Dict[str, Dict[str, int]]: 各数据源的关键词统计
        """
        from collections import defaultdict
        
        # 按数据源分组
        by_source = defaultdict(list)
        for item in items:
            by_source[item.source].append(item)
        
        # 为每个数据源提取关键词
        result = {}
        for source, source_items in by_source.items():
            keywords = self.extract_from_items(source_items)
            result[source] = keywords
        
        return result
    
    def add_stop_words(self, words: List[str]):
        """添加停用词"""
        self.STOP_WORDS.update(words)
    
    def remove_stop_words(self, words: List[str]):
        """移除停用词"""
        self.STOP_WORDS.difference_update(words)


def extract_keywords_for_items(items: List, top_k: int = 5) -> List:
    """
    为 TrendingItem 列表提取关键词并赋值
    
    Args:
        items: 热点数据列表
        top_k: 每个项目提取的关键词数量
        
    Returns:
        List: 带有关键词的数据列表
    """
    extractor = KeywordExtractor(top_k=top_k)
    
    for item in items:
        item.keywords = extractor.extract_from_item(item)
    
    return items


if __name__ == '__main__':
    # 测试
    from src.fetchers import TrendingItem
    
    test_items = [
        TrendingItem(
            source='test',
            title='Show HN: A new AI tool for developers',
            description='This is a machine learning framework built with Python',
            hot_score=1000.0
        ),
        TrendingItem(
            source='test',
            title='OpenAI releases GPT-4 with improved capabilities',
            description='The new model supports multimodal inputs and better reasoning',
            hot_score=2000.0
        ),
    ]
    
    extractor = KeywordExtractor()
    
    print('测试关键词提取:')
    for item in test_items:
        keywords = extractor.extract_from_item(item)
        print(f'标题: {item.title}')
        print(f'关键词: {keywords}')
        print()
    
    # 测试批量提取
    all_keywords = extractor.extract_from_items(test_items)
    print('批量提取结果:')
    print(all_keywords)
