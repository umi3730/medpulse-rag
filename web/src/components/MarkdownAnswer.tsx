import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface Props {
  content: string
  isError?: boolean
}

export default function MarkdownAnswer({ content, isError = false }: Props) {
  return (
    <div className={`max-w-[65ch] text-[0.94rem] leading-7 text-pretty ${isError ? 'text-rose-800' : 'text-[#2f3d38]'}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          h1: ({ children }) => <h1 className="mb-3 mt-6 text-lg font-semibold tracking-[-0.02em] first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-2 mt-5 text-base font-semibold tracking-[-0.015em] first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-2 mt-4 text-[0.94rem] font-semibold first:mt-0">{children}</h3>,
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="my-2 space-y-1 pl-5 marker:text-[#5f8c80]">{children}</ul>,
          ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5 marker:font-mono marker:text-[#5f8c80]">{children}</ol>,
          li: ({ children }) => <li className="pl-1">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold text-[#21312b]">{children}</strong>,
          blockquote: ({ children }) => (
            <blockquote className="my-3 border-l-2 border-[#8eb5aa] bg-[#f0f5f3] py-2 pl-3 pr-4 text-[#496159]">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-[#276255] underline decoration-[#a8c6bd] underline-offset-4 transition-colors hover:text-[#17483d] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6d9d91]"
            >
              {children}
            </a>
          ),
          code: ({ className, children }) => {
            const block = Boolean(className) || String(children).includes('\n')
            return block ? (
              <code className={`${className || ''} block overflow-x-auto rounded-[5px] bg-[#17221e] px-4 py-3 font-mono text-[0.82rem] leading-6 text-[#e5ede9]`}>
                {children}
              </code>
            ) : (
              <code className="rounded-[3px] bg-[#e9efec] px-1.5 py-0.5 font-mono text-[0.84em] text-[#315349]">
                {children}
              </code>
            )
          },
          pre: ({ children }) => <pre className="my-3 overflow-hidden">{children}</pre>,
          table: ({ children }) => (
            <table className="my-3 w-full border-collapse text-left text-[0.84rem]">{children}</table>
          ),
          th: ({ children }) => <th className="border-b border-[#cddbd6] bg-[#f1f5f3] px-3 py-2 font-semibold">{children}</th>,
          td: ({ children }) => <td className="border-b border-[#e0e8e4] px-3 py-2 align-top">{children}</td>,
          hr: () => <hr className="my-5 border-0 border-t border-[#dbe4e0]" />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
