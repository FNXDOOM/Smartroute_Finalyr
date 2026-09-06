import { cn } from '@/lib/utils'

// Lightweight shadcn-style tabs (no extra radix dep).
export function Tabs({ value, onValueChange, className, children }) {
  return <div className={cn(className)} data-value={value} onChange={onValueChange}>{children}</div>
}

export function TabsList({ className, children }) {
  return (
    <div className={cn('inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground', className)}>
      {children}
    </div>
  )
}

export function TabsTrigger({ value, activeValue, onClick, className, children }) {
  const active = value === activeValue
  return (
    <button
      type="button"
      onClick={onClick}
      data-state={active ? 'active' : 'inactive'}
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
        active ? 'bg-background text-foreground shadow' : 'hover:bg-background/50',
        className,
      )}
    >
      {children}
    </button>
  )
}
