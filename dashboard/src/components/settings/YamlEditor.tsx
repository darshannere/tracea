interface YamlEditorProps {
  value: string
  onChange: (value: string) => void
  error?: string
}

export function YamlEditor({ value, onChange, error }: YamlEditorProps) {
  return (
    <div className="relative h-full border rounded-md overflow-hidden flex flex-col">
      {error && (
        <div className="bg-red-50 border-b border-red-200 text-red-700 text-xs px-3 py-1.5 z-10 shrink-0">
          {error}
        </div>
      )}
      <textarea
        className="w-full flex-1 p-3 font-mono text-sm border-0 focus:outline-none resize-none bg-white text-black"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="# Write your YAML config here"
        spellCheck={false}
        autoFocus
      />
    </div>
  )
}
