"""
Syntax Highlighting Engine for Lithium IDE.

Provides language-aware tokenization and colorization for the tk.Text editor.
Uses regex-based tokenization with multi-line construct support.
Tokenization runs only on the visible range for performance.
"""

import re
import tkinter as tk
from typing import Callable, Dict, List, Optional, Tuple

__all__ = ["SyntaxHighlighter", "LANGUAGE_RULES", "TOKEN_TYPES"]

# ---- Token type identifiers ----
TOKEN_TYPES = [
    "keyword",
    "builtin",
    "string",
    "comment",
    "number",
    "function",
    "class",
    "decorator",
    "operator",
    "punctuation",
    "variable",
    "constant",
    "type",
    "string_doc",
]

# ====================================================================
# Language tokenization rules
# ====================================================================
# Each language defines a list of (regex_pattern, token_type) tuples.
# Order matters: earlier patterns at the same position win.
# Patterns using [\s\S] or (?s) are treated as multi-line.
# Python
PYTHON_RULES = [
    (r"#.*$", "comment"),
    # Cadenas simples primero
    (r'"""(?:[^"]|\\.)*"""', "string"),  # Triple double-quote strings
    (r"'''(?:[^']|\\.)*'''", "string"),  # Triple single-quote strings
    (r'[fF]?"[^"\\]*(?:\\.[^"\\]*)*"', "string"),
    (r"[fF]?'[^'\\]*(?:\\.[^'\\]*)*'", "string"),
    # Luego las docstrings
    (r'"""[\s\S]*?"""', "string_doc"),  # Docstrings (less priority)
    (r"'''[\s\S]*?'''", "string_doc"),  # Docstrings (less priority)
    (r"\bdef\s+(\w+)", "function"),
    (r"\bclass\s+(\w+)", "class"),
    (r"@\w+(?:\.\w+)*", "decorator"),
    (r"\b(?:0[xXbBoO])?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?[jJ]?\b", "number"),
    (
        r"\b(?:False|None|True|and|as|assert|async|await|break|class|continue|def|del|"
        r"elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|"
        r"or|pass|raise|return|try|while|with|yield)\b",
        "keyword",
    ),
    (
        r"\b(?:abs|all|any|bin|bool|bytearray|bytes|callable|chr|classmethod|compile|"
        r"complex|delattr|dict|dir|divmod|enumerate|eval|exec|filter|float|format|"
        r"frozenset|getattr|globals|hasattr|hash|help|hex|id|input|int|isinstance|"
        r"issubclass|iter|len|list|locals|map|max|memoryview|min|next|object|oct|open|"
        r"ord|pow|print|property|range|repr|reversed|round|set|setattr|slice|sorted|"
        r"staticmethod|str|sum|super|tuple|type|vars|zip|__import__)\b",
        "builtin",
    ),
    (r"\b(?:self|cls)\b", "variable"),
    (r"[+\-*/%]=?|==|!=|<=|>=|<|>|&&|\|\||!|~|&|\||\^|<<|>>|@|->|\.\.\.", "operator"),
    (r"[\(\)\[\]\{\},;:]", "punctuation"),
]

# JavaScript
JAVASCRIPT_RULES = [
    (r"//.*$", "comment"),
    (r"/\*[\s\S]*?\*/", "comment"),
    (r"/[^/\n][^/\\\n]*(?:\\.[^/\\\n]*)*/[gimsuyd]*", "string"),
    (r"`[^`\\]*(?:\\.[^`\\]*)*`", "string"),
    (r'"[^"\\]*(?:\\.[^"\\]*)*"', "string"),
    (r"'[^'\\]*(?:\\.[^'\\]*)*'", "string"),
    (r"\b(?:0[xXbBoO])?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?\b", "number"),
    (
        r"\b(?:async|await|break|case|catch|class|const|continue|debugger|default|delete|"
        r"do|else|export|extends|finally|for|function|if|import|in|instanceof|let|new|of|"
        r"return|static|super|switch|this|throw|try|typeof|var|void|while|with|yield)\b",
        "keyword",
    ),
    (r"\b(?:true|false|null|undefined|NaN|Infinity)\b", "constant"),
    (
        r"\b(?:Array|Boolean|Date|Error|Function|JSON|Map|Math|Number|Object|Promise|"
        r"RegExp|Set|String|Symbol|console|fetch|setTimeout|setInterval|clearTimeout|"
        r"clearInterval|parseInt|parseFloat|isNaN|isFinite|decodeURI|decodeURIComponent|"
        r"encodeURI|encodeURIComponent|require|module|exports|__dirname|__filename)\b",
        "builtin",
    ),
    (r"\bfunction\s+(\w+)", "function"),
    (r"\bclass\s+(\w+)", "class"),
    (r"[+\-*/%&|^~]=?|==|!=|===|!==|<=|>=|<|>|&&|\|\||!|\?\?|\.\.\.|=>", "operator"),
    (r"[\(\)\[\]\{\},;:]", "punctuation"),
]

# TypeScript (extends JavaScript)
TYPESCRIPT_RULES = JAVASCRIPT_RULES + [
    (
        r"\b(?:interface|type|enum|as|any|boolean|number|string|void|null|undefined|"
        r"never|readonly|implements|abstract|private|protected|public|declare|namespace|"
        r"module|keyof|typeof|infer|satisfies)\b",
        "keyword",
    ),
]

# HTML
HTML_RULES = [
    (r"<!--[\s\S]*?-->", "comment"),
    (r'"(?:[^"\\]|\\.)*"', "string"),
    (r"'(?:[^'\\]|\\.)*'", "string"),
    (r"</?(\w+)[^>]*>", "keyword"),
    (r"<\?[\s\S]*?\?>", "keyword"),
    (
        r"\b(?:class|id|style|src|href|rel|type|name|value|placeholder|disabled|"
        r"checked|selected|data-\w+|aria-\w+|role|onclick|onchange|onsubmit|onload|"
        r"onerror|onkeyup|onkeydown|onkeypress|onmouseover|onmouseout|tabindex|title|alt|"
        r"width|height|target|method|action|for|accept|autocomplete|autofocus|cols|rows|"
        r"max|min|maxlength|minlength|pattern|readonly|required|spellcheck|step)\b",
        "builtin",
    ),
    (r"[<>=/]", "operator"),
]

# CSS
CSS_RULES = [
    (r"/\*[\s\S]*?\*/", "comment"),
    (r'"(?:[^"\\]|\\.)*"', "string"),
    (r"'(?:[^'\\]|\\.)*'", "string"),
    (r"#[0-9a-fA-F]{3,8}\b", "number"),
    (
        r"\b(?:[0-9]+(?:\.[0-9]*)?(?:px|em|rem|vh|vw|%|pt|cm|mm|in|ex|ch|vmin|vmax|deg|"
        r"rad|grad|turn|s|ms|Hz|kHz|dpi|dpcm|dppx)?)\b",
        "number",
    ),
    (r"@[\w-]+", "decorator"),
    (r"\.?-?[_a-zA-Z][_a-zA-Z0-9-]*(?=\s*\{)", "class"),
    (r"#[_a-zA-Z][_a-zA-Z0-9-]*", "constant"),
    (
        r"\b(?:color|background|background-color|margin|padding|border|display|position|"
        r"font|font-size|font-weight|font-family|text-align|text-decoration|width|height|"
        r"max-width|max-height|min-width|min-height|top|right|bottom|left|z-index|overflow|"
        r"float|clear|opacity|visibility|cursor|transform|transition|animation|flex|grid|"
        r"justify-content|align-items|gap|box-shadow|border-radius|outline|list-style|"
        r"vertical-align|white-space|line-height|letter-spacing|word-spacing|text-transform|"
        r"text-indent|direction|unicode-bidi|content|counter-reset|counter-increment|"
        r"page-break|orphans|widows)\b",
        "keyword",
    ),
    (r"[{}:;,>~+*]", "punctuation"),
]

# Java
JAVA_RULES = [
    (r"//.*$", "comment"),
    (r"/\*[\s\S]*?\*/", "comment"),
    (r'"(?:[^"\\]|\\.)*"', "string"),
    (r"'(?:[^'\\]|\\.)'", "string"),
    (r"\b(?:0[xXbB])?[0-9]+(?:\.[0-9]*)?(?:[fFLlDd])?\b", "number"),
    (
        r"\b(?:abstract|assert|boolean|break|byte|case|catch|char|class|const|continue|"
        r"default|do|double|else|enum|extends|final|finally|float|for|goto|if|implements|"
        r"import|instanceof|int|interface|long|native|new|package|private|protected|public|"
        r"return|short|static|strictfp|super|switch|synchronized|this|throw|throws|"
        r"transient|try|void|volatile|while)\b",
        "keyword",
    ),
    (r"\b(?:true|false|null)\b", "constant"),
    (
        r"\b(?:String|Integer|Boolean|Double|Float|Long|Short|Byte|Character|Object|"
        r"Class|System|Math|Arrays|List|ArrayList|Map|HashMap|Set|HashSet|Collection|"
        r"Collections|Iterator|Optional|Stream|Collectors|Comparator|Runnable|Thread|"
        r"Exception|RuntimeException|Error|Throwable)\b",
        "builtin",
    ),
    (r"@\w+(?:\.\w+)*", "decorator"),
    (r"[+\-*/%&|^~]=?|==|!=|<=|>=|<|>|&&|\|\||!|\?", "operator"),
    (r"[\(\)\[\]\{\},;.]", "punctuation"),
]

# C / C++
C_RULES = [
    (r"//.*$", "comment"),
    (r"/\*[\s\S]*?\*/", "comment"),
    (r'"(?:[^"\\]|\\.)*"', "string"),
    (r"'(?:[^'\\]|\\.)'", "string"),
    (r"\b(?:0[xXbB])?[0-9]+(?:\.[0-9]*)?(?:[uUlLfF]+)?\b", "number"),
    (
        r"#\s*include|#\s*define|#\s*ifdef|#\s*ifndef|#\s*if|#\s*else|#\s*elif|#\s*endif|"
        r"#\s*pragma|#\s*error|#\s*warning",
        "decorator",
    ),
    (r"#.*$", "decorator"),
    (
        r"\b(?:auto|break|case|char|const|continue|default|do|double|else|enum|extern|"
        r"float|for|goto|if|inline|int|long|register|restrict|return|short|signed|sizeof|"
        r"static|struct|switch|typedef|union|unsigned|void|volatile|while|"
        r"class|private|protected|public|virtual|override|final|explicit|friend|namespace|"
        r"template|typename|this|throw|try|catch|new|delete|operator|using|constexpr|"
        r"nullptr|decltype|auto|noexcept|static_assert|alignas|alignof|"
        r"std)\b",
        "keyword",
    ),
    (r"\b(?:true|false|nullptr|NULL)\b", "constant"),
    (r"[+\-*/%&|^~]=?|==|!=|<=|>=|<|>|&&|\|\||!|\?|::|->|<<|>>", "operator"),
    (r"[\(\)\[\]\{\},;:]", "punctuation"),
]

# C#
CSHARP_RULES = [
    (r"//.*$", "comment"),
    (r"/\*[\s\S]*?\*/", "comment"),
    (r'@"(?:[^"]|"")*"', "string"),
    (r'"(?:[^"\\]|\\.)*"', "string"),
    (r"'(?:[^'\\]|\\.)'", "string"),
    (r"\b(?:0[xXbB])?[0-9]+(?:\.[0-9]*)?[fFdDlLmM]?\b", "number"),
    (
        r"\b(?:abstract|as|base|bool|break|byte|case|catch|char|checked|class|const|"
        r"continue|decimal|default|delegate|do|double|else|enum|event|explicit|extern|"
        r"false|finally|fixed|float|for|foreach|goto|if|implicit|in|int|interface|"
        r"internal|is|lock|long|namespace|new|null|object|operator|out|override|params|"
        r"private|protected|public|readonly|ref|return|sbyte|sealed|short|sizeof|"
        r"stackalloc|static|string|struct|switch|this|throw|true|try|typeof|uint|ulong|"
        r"unchecked|unsafe|ushort|using|var|virtual|void|volatile|while|async|await|"
        r"yield|record|init|required|file|scoped)\b",
        "keyword",
    ),
    (
        r"\b(?:String|Int32|Int64|Boolean|Double|Single|Decimal|DateTime|TimeSpan|Guid|"
        r"Object|Console|Math|List|Dictionary|IEnumerable|IQueryable|Task|Task<T>|"
        r"CancellationToken|Exception|ArgumentException|ArgumentNullException|"
        r"InvalidOperationException|HttpClient|Action|Func|Tuple|ValueTuple|"
        r"StringBuilder|Array|var|dynamic)\b",
        "builtin",
    ),
    (r"[+\-*/%&|^~]=?|==|!=|<=|>=|<|>|&&|\|\||!|\?|::|->|\?\?|=>", "operator"),
    (r"[\(\)\[\]\{\},;:]", "punctuation"),
]

# Go
GO_RULES = [
    (r"//.*$", "comment"),
    (r"/\*[\s\S]*?\*/", "comment"),
    (r"`[^`]*`", "string"),
    (r'"(?:[^"\\]|\\.)*"', "string"),
    (r"'(?:[^'\\]|\\.)'", "string"),
    (r"\b(?:0[xXbBoO])?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?[i]?\b", "number"),
    (
        r"\b(?:break|case|chan|const|continue|default|defer|else|fallthrough|for|"
        r"func|go|goto|if|import|interface|map|package|range|return|select|struct|"
        r"switch|type|var)\b",
        "keyword",
    ),
    (r"\b(?:true|false|nil|iota)\b", "constant"),
    (
        r"\b(?:string|int|int8|int16|int32|int64|uint|uint8|uint16|uint32|uint64|"
        r"uintptr|float32|float64|complex64|complex128|byte|rune|bool|error)\b",
        "type",
    ),
    (
        r"\b(?:append|cap|close|complex|copy|delete|imag|len|make|new|panic|print|"
        r"println|real|recover)\b",
        "builtin",
    ),
    (r"[+\-*/%&|^]=?|==|!=|<=|>=|<|>|&&|\|\||!|<-|:=|\.\.\.", "operator"),
    (r"[\(\)\[\]\{\},;:]", "punctuation"),
]

# Rust
RUST_RULES = [
    (r"//.*$", "comment"),
    (r"/\*[\s\S]*?\*/", "comment"),
    (r'r#"[^"]*"#', "string"),
    (r'"(?:[^"\\]|\\.)*"', "string"),
    (r"'(?:[^'\\]|\\.|\\x[0-9a-fA-F]{2}|\\u\{[0-9a-fA-F]+\})'", "string"),
    (r"\b(?:0[xXbBoO])?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?[fF]?\b", "number"),
    (
        r"\b(?:as|break|const|continue|crate|else|enum|extern|false|fn|for|if|impl|in|"
        r"let|loop|match|mod|move|mut|pub|ref|return|self|Self|static|struct|super|"
        r"trait|true|type|unsafe|use|where|while|async|await|dyn|abstract|become|box|"
        r"do|final|macro|override|priv|try|typeof|unsized|virtual|yield)\b",
        "keyword",
    ),
    (
        r"\b(?:i8|i16|i32|i64|i128|isize|u8|u16|u32|u64|u128|usize|f32|f64|bool|char|"
        r"str|String|Vec|Box|Option|Result|HashMap|HashSet|BTreeMap|BTreeSet|"
        r"Rc|Arc|Cell|RefCell|Mutex|RwLock|Duration|Path|PathBuf|OsString|OsStr|"
        r"CString|CStr|Cow|Iterator|IntoIterator|FromIterator|Clone|Copy|Debug|Display|"
        r"PartialEq|Eq|PartialOrd|Ord|Hash|Default|From|Into|TryFrom|TryInto|"
        r"Deref|Drop|Sized|Send|Sync|Unpin)\b",
        "type",
    ),
    (r"\b(?:Some|None|Ok|Err)\b", "constant"),
    (
        r"\b(?:println|print|eprintln|eprint|format|format_args|"
        r"assert|assert_eq|assert_ne|debug_assert|debug_assert_eq|debug_assert_ne|"
        r"panic|unreachable|unimplemented|todo|"
        r"include_str|include_bytes|env|option_env|concat|stringify|file|line|column)\b",
        "builtin",
    ),
    (r"[+\-*/%&|^~]=?|==|!=|<=|>=|<|>|&&|\|\||!|\?|::|->|=>|\.\.|=|\.\.\.", "operator"),
    (r"[\(\)\[\]\{\},;:]", "punctuation"),
]

# PHP
PHP_RULES = [
    (r"//.*$", "comment"),
    (r"/\*[\s\S]*?\*/", "comment"),
    (r"#.*$", "comment"),
    (r'<<<[\'"]?\w+[\'"]?[\s\S]*?^\w+;?$', "string", re.MULTILINE),
    (r'"(?:[^"\\$]|\\.|\$[\w]+)*"', "string"),
    (r"'(?:[^'\\]|\\.)*'", "string"),
    (r"\b(?:0[xXbB])?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?\b", "number"),
    (r"\$\w+", "variable"),
    (
        r"\b(?:abstract|and|array|as|break|callable|case|catch|class|clone|const|"
        r"continue|declare|default|die|do|echo|else|elseif|empty|enddeclare|endfor|"
        r"endforeach|endif|endswitch|endwhile|eval|exit|extends|final|finally|fn|for|"
        r"foreach|function|global|goto|if|implements|include|include_once|instanceof|"
        r"insteadof|interface|isset|list|match|namespace|new|or|print|private|protected|"
        r"public|readonly|require|require_once|return|static|switch|throw|trait|try|"
        r"unset|use|var|while|xor|yield)\b",
        "keyword",
    ),
    (r"\b(?:true|false|null|TRUE|FALSE|NULL)\b", "constant"),
    (r"[+\-*/%.&|^~]=?|==|!=|===|!==|<=>|<=|>=|<|>|&&|\|\||!|->|::", "operator"),
    (r"[\(\)\[\]\{\},;]", "punctuation"),
]

# Ruby
RUBY_RULES = [
    (r"#.*$", "comment"),
    (r"=begin[\s\S]*?=end", "comment"),
    (r"%[qQrRwWx]?\{[\s\S]*?}", "string"),
    (r'"[^"\\]*(?:\\.[^"\\]*)*"', "string"),
    (r"'[^'\\]*(?:\\.[^'\\]*)*'", "string"),
    (r":\w+", "string"),
    (r"\b(?:0[xXbBoOdD])?[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?[rRiI]?\b", "number"),
    (r":\w+", "constant"),
    (
        r"\b(?:BEGIN|END|alias|and|begin|break|case|class|def|defined\?|do|else|elsif|"
        r"end|ensure|false|for|if|in|module|next|nil|not|or|redo|rescue|retry|return|"
        r"self|super|then|true|undef|unless|until|when|while|yield)\b",
        "keyword",
    ),
    (
        r"\b(?:attr_accessor|attr_reader|attr_writer|include|extend|prepend|require|"
        r"require_relative|load|autoload|private|protected|public|module_function|"
        r"raise|fail|catch|throw|lambda|proc|puts|print|p|puts|gets|chomp|"
        r"each|map|select|reject|reduce|inject|sort|filter|find|collect|"
        r"initialize|new|method_missing|respond_to\?|send|public_send|"
        r"puts|raise|fail|sleep|loop|block_given\?)\b",
        "builtin",
    ),
    (r"@\w+|@@\w+", "variable"),
    (r"[+\-*/%&|^~]=?|==|!=|<=|>=|<|>|&&|\|\||!|=>|::|\.\.|\.\.\.", "operator"),
    (r"[\(\)\[\]\{\},;]", "punctuation"),
]

# SQL
SQL_RULES = [
    (r"--.*$", "comment"),
    (r"/\*[\s\S]*?\*/", "comment"),
    (r'"(?:[^"\\]|\\.)*"', "string"),
    (r"'(?:[^'\\]|\\.)*'", "string"),
    (r"\b[0-9]+(?:\.[0-9]*)?\b", "number"),
    (
        r"\b(?:SELECT|FROM|WHERE|INSERT|INTO|VALUES|UPDATE|SET|DELETE|CREATE|TABLE|"
        r"ALTER|DROP|INDEX|VIEW|TRIGGER|FUNCTION|PROCEDURE|IF|ELSE|THEN|WHEN|"
        r"AND|OR|NOT|IN|BETWEEN|LIKE|IS|NULL|EXISTS|ALL|ANY|SOME|UNION|ALL|"
        r"JOIN|INNER|LEFT|RIGHT|OUTER|FULL|CROSS|ON|AS|ORDER|BY|GROUP|HAVING|"
        r"LIMIT|OFFSET|ASC|DESC|DISTINCT|CASE|WHEN|THEN|ELSE|END|BEGIN|COMMIT|"
        r"ROLLBACK|GRANT|REVOKE|PRIMARY|KEY|FOREIGN|REFERENCES|CASCADE|DEFAULT|"
        r"CHECK|CONSTRAINT|UNIQUE|AUTO_INCREMENT|SERIAL|BIGINT|INT|INTEGER|SMALLINT|"
        r"TINYINT|NUMERIC|DECIMAL|FLOAT|DOUBLE|REAL|DATE|TIME|DATETIME|TIMESTAMP|"
        r"CHAR|VARCHAR|TEXT|BLOB|ENUM|SET|BOOLEAN|BOOL|TRANSACTION)\b",
        "keyword",
    ),
    (
        r"\b(?:COUNT|SUM|AVG|MIN|MAX|COALESCE|NULLIF|CAST|CONVERT|SUBSTRING|"
        r"UPPER|LOWER|TRIM|LENGTH|REPLACE|CONCAT|NOW|CURDATE|CURTIME|"
        r"DATE_FORMAT|EXTRACT|YEAR|MONTH|DAY|HOUR|MINUTE|SECOND|"
        r"GROUP_CONCAT|ROW_NUMBER|RANK|DENSE_RANK|LEAD|LAG|FIRST_VALUE|LAST_VALUE)\b",
        "builtin",
    ),
    (r"[=<>!+\-*/%(),;.]", "operator"),
]

# Bash / Shell
BASH_RULES = [
    (r"#.*$", "comment"),
    (r"`[^`]*`", "string"),
    (r'"(?:[^"\\$]|\\.|\$\{?\w+\}?)*"', "string"),
    (r"'(?:[^'\\]|\\.)*'", "string"),
    (r"\$\([\s\S]*?\)", "string"),
    (r"\$\{?\w+\}?", "variable"),
    (r"\b[0-9]+(?:\.[0-9]*)?\b", "number"),
    (
        r"\b(?:if|then|else|elif|fi|for|while|until|do|done|case|esac|in|"
        r"function|return|exit|break|continue|select|time|"
        r"declare|typeset|local|export|readonly|unset|"
        r"echo|printf|read|source|\.|exec|eval|let|shift|"
        r"cd|pwd|ls|mkdir|rm|cp|mv|cat|grep|sed|awk|find|xargs|"
        r"chmod|chown|touch|head|tail|sort|uniq|wc|diff|"
        r"set|unset|alias|unalias|type|command|builtin|enable|"
        r"trap|kill|wait|bg|fg|jobs|disown|suspend|"
        r"[\[\]]|test|true|false)\b",
        "keyword",
    ),
    (r"[=<>!&|;]", "operator"),
    (r"[\(\)\{\}]", "punctuation"),
]

# YAML
YAML_RULES = [
    (r"#.*$", "comment"),
    (r'"[^"\\]*(?:\\.[^"\\]*)*"', "string"),
    (r"'[^'\\]*(?:\\.[^'\\]*)*'", "string"),
    (r"\b(?:true|false|yes|no|on|off|null|~)\b", "constant"),
    (r"\b[0-9]+(?:\.[0-9]*)?\b", "number"),
    (r"^[\s]*[-][\s]", "punctuation"),
    (r"^[\s]*[\w_/\-.]+:", "keyword"),
    (r"[\[\[\]\{\},]", "punctuation"),
]

# Markdown
MARKDOWN_RULES = [
    (r"<!--[\s\S]*?-->", "comment"),
    (r"```[\s\S]*?```", "string"),
    (r"`[^`]+`", "string"),
    (r"^#{1,6}\s+.*$", "keyword"),
    (r"\*\*[\s\S]*?\*\*", "string_doc"),
    (r"__[\s\S]*?__", "string_doc"),
    (r"\*[\s\S]*?\*", "string_doc"),
    (r"_[\s\S]*?_", "string_doc"),
    (r"^[\s]*[-*+]\s", "punctuation"),
    (r"^[\s]*\d+\.\s", "number"),
    (r"\[([^\]]+)\]\(([^)]+)\)", "constant"),
    (r"!\[([^\]]*)\]\(([^)]+)\)", "builtin"),
    (r"^[\s]*>.*$", "decorator"),
    (r"^---$", "operator"),
]

# ====================================================================
# Language rules map
# ====================================================================

LANGUAGE_RULES: Dict[str, List[Tuple[str, str]]] = {
    "Python": PYTHON_RULES,
    "JavaScript": JAVASCRIPT_RULES,
    "TypeScript": TYPESCRIPT_RULES,
    "JSX": JAVASCRIPT_RULES,
    "TSX": TYPESCRIPT_RULES,
    "HTML": HTML_RULES,
    "CSS": CSS_RULES,
    "SCSS": CSS_RULES,
    "Sass": CSS_RULES,
    "Less": CSS_RULES,
    "Java": JAVA_RULES,
    "C": C_RULES,
    "C++": C_RULES,
    "C#": CSHARP_RULES,
    "Objective-C": C_RULES,
    "Go": GO_RULES,
    "Rust": RUST_RULES,
    "PHP": PHP_RULES,
    "Ruby": RUBY_RULES,
    "SQL": SQL_RULES,
    "Bash": BASH_RULES,
    "Shell": BASH_RULES,
    "Zsh": BASH_RULES,
    "YAML": YAML_RULES,
    "Markdown": MARKDOWN_RULES,
    "JSON": [],
    "XML": HTML_RULES,
    "SVG": HTML_RULES,
}

# ====================================================================
# Default token colors (can be overridden by themes)
# ====================================================================

DEFAULT_TOKEN_COLORS: Dict[str, str] = {
    "keyword": "#cba6f7",  # mauve / purple
    "builtin": "#89b4fa",  # blue
    "string": "#a6e3a1",  # green
    "comment": "#585b70",  # gray
    "number": "#fab387",  # peach
    "function": "#89dceb",  # teal
    "class": "#f9e2af",  # yellow
    "decorator": "#f9e2af",  # yellow
    "operator": "#89dceb",  # teal
    "punctuation": "#bac2de",  # light gray
    "variable": "#89b4fa",  # blue
    "constant": "#fab387",  # peach
    "type": "#f9e2af",  # yellow
    "string_doc": "#6c7086",  # dark gray
}

# ====================================================================
# Syntax Highlighter class
# ====================================================================


class SyntaxHighlighter:
    """
    Manages syntax highlighting for a tk.Text editor widget.

    Usage:
        highlighter = SyntaxHighlighter(editor_widget, language_getter)
        highlighter.highlight_visible()

    Bind it to <KeyRelease> and <MouseWheel> for live highlighting.
    """

    def __init__(
        self,
        editor: tk.Text,
        language_getter: Callable[[], str],
        token_colors: Optional[Dict[str, str]] = None,
    ):
        """
        Args:
            editor: The tk.Text widget to highlight.
            language_getter: Callable returning the current language name.
                             Must match a key in LANGUAGE_RULES, e.g. "Python".
            token_colors: Optional dict mapping token type to hex color.
                          Falls back to DEFAULT_TOKEN_COLORS.
        """
        self.editor = editor
        self._language_getter = language_getter
        self._running = False
        self._schedule_id: Optional[str] = None
        self._initial_highlight_done = False
        self._token_colors = dict(DEFAULT_TOKEN_COLORS)
        if token_colors:
            self._token_colors.update(token_colors)

        # Setup tags for all token types
        self._tag_priority()
        self._rebuild_tags()

        # Bind to editor changes
        self.editor.bind("<<Modified>>", self._on_modified, add="+")

    def _tag_priority(self):
        """Ensure syntax tags are above other text tags."""
        # Tag raise will be done per-tag in _rebuild_tags
        pass

    def _rebuild_tags(self):
        """(Re)create or update all token tags with their foreground colors."""
        for token_type, color in self._token_colors.items():
            tag_name = f"syn_{token_type}"
            try:
                # Try to configure the tag; if it doesn't exist, tag_config creates it
                self.editor.tag_config(tag_name, foreground=color)
                self.editor.tag_raise(tag_name)
            except Exception as e:
                print(f"DEBUG: Error in _rebuild_tags: {e}")
                pass

    def _apply_tags(self, tokens: List[Tuple[int, int, int, str]]):
        """Helper to apply token tags to the editor, handling sorting, overlaps, and priority."""
        try:
            type_priority = {t: i for i, t in enumerate(TOKEN_TYPES)}

            def sort_key(t):
                return (t[0], t[1], type_priority.get(t[3], 99))

            tokens.sort(key=sort_key)

            # Deduplicate overlapping regions using a greedy approach
            # For each line, track occupied [start, end) intervals
            line_tokens: Dict[int, List[Tuple[int, int, str]]] = {}
            for lineno, col_start, col_end, token_type in tokens:
                if col_start >= col_end:
                    continue
                if lineno not in line_tokens:
                    line_tokens[lineno] = []
                line_tokens[lineno].append((col_start, col_end, token_type))

            # Apply tags per line
            for lineno, items in line_tokens.items():
                line_str = str(lineno)
                for col_start, col_end, token_type in items:
                    start_index = f"{line_str}.{col_start}"
                    end_index = f"{line_str}.{col_end}"
                    tag_name = f"syn_{token_type}"
                    try:
                        self.editor.tag_add(tag_name, start_index, end_index)
                    except Exception as e:
                        print(
                            f"DEBUG: Failed to tag_add {tag_name} at {start_index}-{end_index}: {e}"
                        )
        except Exception as e:
            print(f"DEBUG: Error in _apply_tags: {e}")

    def update_token_color(self, token_type: str, color: str):
        """Update the color for a specific token type and reapply."""
        if token_type in self._token_colors:
            self._token_colors[token_type] = color
            tag_name = f"syn_{token_type}"
            try:
                self.editor.tag_config(tag_name, foreground=color)
                self.editor.tag_raise(tag_name)
            except Exception as e:
                print(f"DEBUG: Error in update_token_color: {e}")
                pass

    def get_token_colors(self) -> Dict[str, str]:
        """Return the current token color map."""
        return dict(self._token_colors)

    def set_token_colors(self, colors: Dict[str, str]):
        """Replace all token colors and rebuild tags."""
        self._token_colors.update(colors)
        self._rebuild_tags()

    @property
    def language(self) -> str:
        """Get the current language name from the getter."""
        return self._language_getter()

    def get_rules(self) -> Optional[List[Tuple[str, str]]]:
        """Get the tokenization rules for the current language."""
        return LANGUAGE_RULES.get(self.language, None)

    def _on_modified(self, event=None):
        """Called when the text widget's modified flag changes."""
        if self.editor.edit_modified():
            if not self._initial_highlight_done:
                # Check if the editor actually has content
                content = self.editor.get("1.0", "end-1c")
                if content:
                    self._initial_highlight_done = True
                    self.highlight_all()
                else:
                    self.schedule_highlight()
            else:
                self.schedule_highlight()
            self.editor.edit_modified(False)

    def schedule_highlight(self, delay_ms: int = 200):
        """Schedule a highlight pass with debouncing."""
        if self._schedule_id:
            try:
                self.editor.after_cancel(self._schedule_id)
            except Exception:
                pass
        self._schedule_id = self.editor.after(delay_ms, self.highlight_visible)

    def highlight_visible(self):
        """
        Highlight only the visible portion of the text for performance.

        Falls back to highlighting the full document if the visible range
        cannot be determined.
        """
        if self._running:
            return
        self._running = True
        self._schedule_id = None

        try:
            rules = self.get_rules()
            if not rules:
                return

            # Determine visible range
            first_line = self.editor.index("@0,0")
            last_line = self.editor.index("@0,%d" % self.editor.winfo_height())

            if not first_line or not last_line:
                return

            # Remove old syntax tags only in the visible range
            for tag_name in self.editor.tag_names():
                if tag_name.startswith("syn_"):
                    try:
                        self.editor.tag_remove(tag_name, first_line, last_line)
                    except Exception as e:
                        print(
                            f"DEBUG: Error removing tag {tag_name} in visible range {first_line}-{last_line}: {e}"
                        )
                        pass

            # Tokenize the visible text
            text = self.editor.get(first_line, last_line)
            # Map from absolute to relative line numbers
            abs_start_line = int(first_line.split(".")[0])

            tokens: List[
                Tuple[int, int, int, str]
            ] = []  # (abs_lineno, col_start, col_end, token_type)
            for rule_pattern, token_type in rules:
                flags = 0
                pattern = rule_pattern
                # Check for multi-line patterns
                for match in re.finditer(pattern, text, flags):
                    start_rel = match.start()
                    end_rel = match.end()

                    # Convert relative position to absolute line/col
                    rel_before = text[:start_rel]
                    abs_lineno = abs_start_line + rel_before.count("\n")
                    last_newline = rel_before.rfind("\n")
                    if last_newline >= 0:
                        col_start = start_rel - last_newline - 1
                    else:
                        col_start = start_rel

                    rel_span = text[:end_rel]
                    last_newline_end = rel_span.rfind("\n")
                    if last_newline_end >= 0:
                        col_end = end_rel - last_newline_end - 1
                    else:
                        col_end = end_rel

                    # For function/class rules with group(1), extract the name
                    if token_type in ("function", "class"):
                        # The full match starts with 'def ' or 'class ' etc.
                        # We only highlight the name part (group 1)
                        gstart = match.start(1)
                        gend = match.end(1)
                        rel_gstart = gstart
                        rel_gend = gend

                        g_before = text[:rel_gstart]
                        g_abs_lineno = abs_start_line + g_before.count("\n")
                        g_last_newline = g_before.rfind("\n")
                        g_col_start = (
                            rel_gstart - g_last_newline - 1
                            if g_last_newline >= 0
                            else rel_gstart
                        )

                        g_span = text[:rel_gend]
                        g_last_newline_end = g_span.rfind("\n")
                        g_col_end = (
                            rel_gend - g_last_newline_end - 1
                            if g_last_newline_end >= 0
                            else rel_gend
                        )

                        tokens.append(
                            (g_abs_lineno, g_col_start, g_col_end, token_type)
                        )
                    else:
                        tokens.append((abs_lineno, col_start, col_end, token_type))

            # Apply tags, handling overlaps by preferring earlier rules
            self._apply_tags(tokens)
        except Exception as e:
            print(f"DEBUG: Error in highlight_visible: {e}")
        finally:
            self._running = False

    def highlight_all(self):
        """Highlight the entire editor content (may be slow for large files)."""
        # Remove old syntax tags globally
        for tag_name in self.editor.tag_names():
            if tag_name.startswith("syn_"):
                try:
                    self.editor.tag_remove(tag_name, "1.0", tk.END)
                except Exception:
                    pass

        rules = self.get_rules()
        if not rules:
            return

        text = self.editor.get("1.0", tk.END)

        tokens: List[Tuple[int, int, int, str]] = []

        for rule_pattern, token_type in rules:
            for match in re.finditer(rule_pattern, text):
                start_rel = match.start()
                end_rel = match.end()

                rel_before = text[:start_rel]
                abs_lineno = 1 + rel_before.count("\n")
                last_newline = rel_before.rfind("\n")
                col_start = (
                    start_rel - last_newline - 1 if last_newline >= 0 else start_rel
                )

                rel_span = text[:end_rel]
                last_newline_end = rel_span.rfind("\n")
                col_end = (
                    end_rel - last_newline_end - 1 if last_newline_end >= 0 else end_rel
                )

                if token_type in ("function", "class"):
                    gstart = match.start(1)
                    gend = match.end(1)
                    g_before = text[:gstart]
                    g_abs_lineno = 1 + g_before.count("\n")
                    g_last_newline = g_before.rfind("\n")
                    g_col_start = (
                        gstart - g_last_newline - 1 if g_last_newline >= 0 else gstart
                    )

                    g_span = text[:gend]
                    g_last_newline_end = g_span.rfind("\n")
                    g_col_end = (
                        gend - g_last_newline_end - 1
                        if g_last_newline_end >= 0
                        else gend
                    )

                    tokens.append((g_abs_lineno, g_col_start, g_col_end, token_type))
                else:
                    tokens.append((abs_lineno, col_start, col_end, token_type))

        # Apply tags, handling overlaps by preferring earlier rules
        self._apply_tags(tokens)

    def set_language(self, language: str):
        """
        Notify that the language changed. Triggers a full re-highlight.
        """
        self.highlight_all()

    def destroy(self):
        """Clean up bindings."""
        try:
            self.editor.unbind("<<Modified>>", self._on_modified)
        except Exception:
            pass
        self._schedule_id = None
