/* eslint-disable react-refresh/only-export-components */
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

/* Restrained badges: neutral by default, semantic sparingly. */
const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black dark:focus-visible:outline-white',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-black text-white dark:border-transparent dark:bg-white dark:text-black',
        secondary: 'border-[#E2E2E2] bg-[#F6F6F6] text-[#333333] dark:border-[#333333] dark:bg-[#2A2A2A] dark:text-[#E2E2E2]',
        destructive: 'border-[#D93025]/25 bg-[#D93025]/10 text-[#D93025]',
        success: 'border-[#276EF1]/25 bg-[#276EF1]/10 text-[#276EF1]',
        warning: 'border-[#F5A623]/30 bg-[#F5A623]/10 text-[#7A4A00] dark:text-[#F5A623]',
        outline: 'border-[#D6D6D6] bg-transparent text-[#333333] dark:border-[#333333] dark:text-[#E2E2E2]',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

function Badge({ className, variant, ...props }) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
