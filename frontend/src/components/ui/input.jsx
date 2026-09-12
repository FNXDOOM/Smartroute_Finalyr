import * as React from 'react'
import { cn } from '@/lib/utils'

/* Uber-inspired input: white, 1px #D6D6D6, 48–52px height, 8px radius.
   Focus: black border + soft ring. Placeholder neutral gray. */
const Input = React.forwardRef(({ className, type, ...props }, ref) => (
  <input
    type={type}
    ref={ref}
    className={cn(
      'flex h-[52px] w-full rounded-lg border border-[#D6D6D6] bg-white px-4 py-2 text-[15px] text-[#111111] transition-[border-color,box-shadow] duration-150 placeholder:text-[#8A8A8A] hover:border-[#AFAFAF] focus-visible:outline-none focus-visible:border-black focus-visible:ring-[3px] focus-visible:ring-black/10 disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#333333] dark:bg-[#1F1F1F] dark:text-white dark:placeholder:text-[#8A8A8A] dark:focus-visible:border-white dark:focus-visible:ring-white/15 file:border-0 file:bg-transparent file:text-sm file:font-medium',
      className,
    )}
    {...props}
  />
))
Input.displayName = 'Input'

export { Input }
