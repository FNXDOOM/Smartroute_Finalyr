import { cn } from "cn"

/* Minimal premium tables: strong header, comfortable rows, hover, mobile scroll. */
function Table({
  className,
  ...props
}) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto rounded-xl border border-[#E2E2E2] bg-white dark:border-[#333333] dark:bg-[#1F1F1F]"
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({
  className,
  ...props
}) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b [&_tr]:border-[#E2E2E2] dark:[&_tr]:border-[#333333]", className)}
      {...props}
    />
  )
}

function TableBody({
  className,
  ...props
}) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({
  className,
  ...props
}) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t border-[#E2E2E2] bg-[#F6F6F6] font-medium dark:border-[#333333] dark:bg-[#2A2A2A] [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({
  className,
  ...props
}) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b border-[#EEEEEE] transition-colors duration-150 hover:bg-[#F6F6F6] has-aria-expanded:bg-[#F6F6F6] data-[state=selected]:bg-[#EEEEEE] dark:border-[#2A2A2A] dark:hover:bg-[#2A2A2A]",
        className
      )}
      {...props}
    />
  )
}

function TableHead({
  className,
  ...props
}) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-12 px-4 text-left align-middle text-[11px] font-semibold uppercase tracking-[0.06em] whitespace-nowrap text-[#6B6B6B] dark:text-[#AFAFAF] [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCell({
  className,
  ...props
}) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "min-h-[52px] px-4 py-3.5 align-middle text-[14px] whitespace-nowrap text-[#111111] dark:text-white [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-[#6B6B6B]", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
