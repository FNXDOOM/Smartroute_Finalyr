/* eslint-disable react-refresh/only-export-components */
import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva } from "class-variance-authority";
import { cn } from "cn"

/*
 * Uber-inspired button system:
 * - Primary: black bg / white text, 48px min-height, 8px radius, 600 weight
 * - Secondary: white bg / black text / 1px #D6D6D6
 * - Text: no bg/border, understated hover
 * - 150–200ms transitions, visible focus
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-lg border font-semibold whitespace-nowrap transition-[background-color,border-color,color,transform,box-shadow] duration-200 outline-none select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-black dark:focus-visible:outline-white active:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-[#D93025] [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border-black bg-black text-white hover:bg-[#1F1F1F] hover:border-[#1F1F1F] dark:border-white dark:bg-white dark:text-black dark:hover:bg-[#E2E2E2] dark:hover:border-[#E2E2E2]",
        outline:
          "border-[#D6D6D6] bg-white text-black hover:bg-[#F6F6F6] hover:border-[#AFAFAF] dark:border-[#333333] dark:bg-transparent dark:text-white dark:hover:bg-[#1F1F1F]",
        secondary:
          "border-transparent bg-[#F6F6F6] text-black hover:bg-[#EEEEEE] dark:border-transparent dark:bg-[#1F1F1F] dark:text-white dark:hover:bg-[#2A2A2A]",
        ghost:
          "border-transparent text-[#333333] hover:bg-[#F6F6F6] hover:text-black dark:text-[#AFAFAF] dark:hover:bg-[#1F1F1F] dark:hover:text-white",
        destructive:
          "border-transparent bg-[#D93025]/10 text-[#D93025] hover:bg-[#D93025]/15 dark:bg-[#D93025]/20",
        link: "border-transparent font-semibold text-black underline-offset-4 hover:underline dark:text-white",
      },
      size: {
        default:
          "h-12 gap-2 px-6 text-[15px] has-data-[icon=inline-end]:pr-5 has-data-[icon=inline-start]:pl-5",
        xs: "h-8 gap-1 rounded-md px-3 text-xs",
        sm: "h-10 gap-1.5 rounded-lg px-4 text-sm has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-[52px] gap-2 px-7 text-base has-data-[icon=inline-end]:pr-6 has-data-[icon=inline-start]:pl-6",
        icon: "size-11",
        "icon-xs":
          "size-8 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm":
          "size-10 rounded-lg",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
