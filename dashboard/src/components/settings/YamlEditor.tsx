import Editor from '@monaco-editor/react'
import type { OnMount } from '@monaco-editor/react'

interface YamlEditorProps {
  value: string
  onChange: (value: string) => void
  error?: string
}

export function YamlEditor({ value, onChange, error }: YamlEditorProps) {
  const handleMount: OnMount = (editor) => {
    // Auto-focus editor on mount
    editor.focus()
  }

  return (
    <div className="relative h-full border rounded-md overflow-hidden">
      {error && (
        <div className="absolute top-0 left-0 right-0 bg-red-50 border-b border-red-200 text-red-700 text-xs px-3 py-1.5 z-10">
          {error}
        </div>
      )}
      <Editor
        language="yaml"
        value={value}
        onChange={(v) => onChange(v ?? '')}
        onMount={handleMount}
        height="100%"
        theme="vs-light"
        options={{
          minimap: { enabled: false },
          lineNumbers: 'on',
          scrollBeyondLastLine: false,
          fontSize: 13,
          tabSize: 2,
          wordWrap: 'on',
          folding: true,
          renderLineHighlight: 'line',
          scrollbar: {
            verticalScrollbarSize: 8,
            horizontalScrollbarSize: 8,
          },
        }}
      />
    </div>
  )
}
