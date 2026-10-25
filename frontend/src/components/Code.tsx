import * as React from 'react'
import Prism from 'prismjs'
import 'prismjs/components/prism-sql'
import 'prismjs/components/prism-json'
import { Check, Copy } from 'lucide-react'
import { cn } from '@/lib/utils'

const g = Prism.languages as any
if (!g.dax) {
  g.dax = {
    comment: [{ pattern: /\/\/.*|--.*/, greedy: true }, { pattern: /\/\*[\s\S]*?\*\//, greedy: true }],
    string: { pattern: /"(?:[^"]|"")*"/, greedy: true },
    table: { pattern: /'(?:[^']|'')+'(?=\s*\[)|\b[A-Za-z_][\w]*(?=\[)/, greedy: true },
    column: { pattern: /\[(?:[^\]]|\]\])+\]/, greedy: true },
    keyword: /\b(?:VAR|RETURN|IN|NOT|AND|OR|TRUE|FALSE|BLANK|DEFINE|EVALUATE|MEASURE|ORDER BY|ASC|DESC)\b/i,
    function: /\b[A-Z][A-Z0-9.]*(?=\s*\()/i,
    number: /\b\d+(?:\.\d+)?\b/,
    operator: /&&|\|\||[-+*/=<>&^]|<>|<=|>=/,
    punctuation: /[(),{}]/,
  }
  g.m = {
    comment: [{ pattern: /\/\/.*/, greedy: true }, { pattern: /\/\*[\s\S]*?\*\//, greedy: true }],
    string: { pattern: /"(?:[^"]|"")*"/, greedy: true },
    variable: /#"(?:[^"]|"")*"/,
    keyword: /\b(?:let|in|each|if|then|else|true|false|null|type|meta|as|is|and|or|not|try|otherwise|error|section|shared)\b/,
    function: /\b[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+(?=\s*\()/,
    column: /\[[^\]]+\]/,
    number: /\b\d+(?:\.\d+)?\b/,
    operator: /=>|<>|<=|>=|[-+*/=<>&]/,
    punctuation: /[(),{}[\];]/,
  }
}

function escapeRe(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function Code({ code, lang, highlight = [], className, maxHeight = 360 }: { code: string; lang: string; highlight?: string[]; className?: string; maxHeight?: number }) {
  const [copied, setCopied] = React.useState(false)
  const html = React.useMemo(() => {
    const grammar = g[lang] ?? g.sql
    let out = Prism.highlight(code, grammar, lang)
    const terms = highlight.filter((t) => t && t.length > 1)
    if (terms.length) {
      const re = new RegExp(`(?<![\\w])(${terms.map(escapeRe).join('|')})(?![\\w])`, 'gi')
      // only replace inside text nodes (outside of tags)
      out = out.replace(/(^|>)([^<]+)/g, (_m, a: string, text: string) => a + text.replace(re, '<mark class="code-hit">$1</mark>'))
    }
    return out
  }, [code, lang, highlight])
  return (
    <div className={cn('group relative rounded-md border bg-muted/40', className)}>
      <button
        onClick={() => {
          navigator.clipboard?.writeText(code)
          setCopied(true)
          setTimeout(() => setCopied(false), 1200)
        }}
        className="absolute right-2 top-2 rounded-md border bg-card p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
        title="Copy"
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
      <pre className="code-block overflow-auto p-3 scrollbar-thin" style={{ maxHeight }}>
        <code dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  )
}
