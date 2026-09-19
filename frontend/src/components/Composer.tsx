import { useEffect, useRef, type ReactNode } from 'react'

type Props = {
  value: string
  placeholder: string
  disabled?: boolean
  label?: string
  onChange: (value: string) => void
  onSubmit?: () => void
  submitDisabled?: boolean
  actions: ReactNode
}

const MAX_HEIGHT = 220

export function Composer({
  value,
  placeholder,
  disabled,
  label,
  onChange,
  onSubmit,
  submitDisabled,
  actions,
}: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(input.scrollHeight, MAX_HEIGHT)}px`
  }, [value])

  return (
    <div className={`composer ${disabled ? 'disabled' : ''}`}>
      {label && <label htmlFor="composer-input">{label}</label>}
      <textarea
        id="composer-input"
        ref={inputRef}
        rows={1}
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey && onSubmit) {
            event.preventDefault()
            if (!submitDisabled) onSubmit()
          }
        }}
      />
      <div className="composer-actions">{actions}</div>
    </div>
  )
}

export function SendButton({
  busy,
  disabled,
  title,
  onClick,
}: {
  busy?: boolean
  disabled?: boolean
  title: string
  onClick: () => void
}) {
  return (
    <button
      className="send"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
    >
      {busy ? (
        <span className="spinner" />
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 19V6M6 12l6-6 6 6"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </button>
  )
}
