/* eslint-disable react-refresh/only-export-components */
import { Bell, CheckCircle2, ChevronRight, Inbox, LogOut, Menu, User as UserIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Separator } from '@/components/ui/separator'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ThemeToggle } from '@/components/theme-toggle'

// View titles for sidebar router.
export const VIEW_META = {
  home: { title: 'Book a ride', crumb: 'Passenger / Home' },
  trips: { title: 'My trips', crumb: 'Passenger / Trips' },
  'recent-rides': { title: 'Recent rides', crumb: 'Passenger / Recent' },
  'trip-detail': { title: 'Trip detail', crumb: 'Passenger / Trip' },
  tracking: { title: 'Live tracking', crumb: 'Passenger / Tracking' },
  inbox: { title: 'Notifications', crumb: 'Workspace / Inbox' },
  profile: { title: 'Profile', crumb: 'Workspace / Profile' },
  'driver-apply': { title: 'Become a driver', crumb: 'Workspace / Driver application' },
  'driver-home': { title: 'Driver dashboard', crumb: 'Driver / Overview' },
  'driver-map': { title: 'Live navigation', crumb: 'Driver / Map' },
  'driver-routes': { title: 'My routes', crumb: 'Driver / Routes' },
  'presentation-demo': { title: 'Presentation demo', crumb: 'Demo / Shared transit simulation' },
  'admin-overview': { title: 'Operations overview', crumb: 'Admin / Overview' },
  'admin-rides': { title: 'Rides', crumb: 'Admin / Rides' },
  'admin-vehicles': { title: 'Fleet', crumb: 'Admin / Fleet' },
  'admin-drivers': { title: 'Drivers', crumb: 'Admin / Drivers' },
  'admin-cluster': { title: 'Grouping', crumb: 'Admin / Grouping' },
  'admin-routes': { title: 'Routes', crumb: 'Admin / Routes' },
  'admin-analytics': { title: 'Analytics', crumb: 'Admin / Analytics' },
  'admin-jobs': { title: 'Jobs', crumb: 'Admin / Jobs' },
  'admin-heatmap': { title: 'Heatmap', crumb: 'Admin / Heatmap' },
}

export default function AppTopBar({
  user,
  view,
  setView,
  unreadCount = 0,
  notifications = [],
  onOpenNotifications,
  onLogout,
  onOpenMobileNav,
  theme,
  onToggleTheme,
}) {
  const meta = VIEW_META[view] || { title: 'SmartRoute', crumb: 'Workspace' }
  const recent = notifications.slice(0, 5)

  return (
    <header className="app-topbar sticky top-0 z-40 flex h-[68px] shrink-0 items-center gap-3 border-b border-[#E2E2E2] bg-white px-4 md:px-8 dark:border-[#333333] dark:bg-black">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onOpenMobileNav}
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <div className="min-w-0 flex-1">
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[12px] font-medium text-[#8A8A8A]">
          <span className="hidden truncate sm:inline">{meta.crumb.split(' / ')[0]}</span>
          <ChevronRight className="hidden h-3 w-3 sm:inline" aria-hidden="true" />
          <span className="truncate text-[#545454] dark:text-[#AFAFAF]">{meta.crumb.split(' / ')[1] || meta.crumb}</span>
        </nav>
        <h1 className="truncate text-[18px] font-semibold leading-tight tracking-[-0.01em]">{meta.title}</h1>
      </div>

      <div className="flex items-center gap-1">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="ghost" size="icon" className="relative h-11 w-11 rounded-lg" aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}>
                <Bell className="h-5 w-5" />
                {unreadCount > 0 && (
                  <Badge className="absolute -right-0.5 -top-0.5 h-5 min-w-5 justify-center border-0 bg-black px-1.5 text-[11px] font-bold leading-none text-white dark:bg-white dark:text-black">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </Badge>
                )}
              </Button>
            }
          />
          <DropdownMenuContent align="end" sideOffset={8} className="w-80 rounded-xl border-[#E2E2E2] p-1.5 shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
            <DropdownMenuLabel className="flex items-center justify-between px-2.5 py-2">
              <span className="text-[14px] font-semibold">Notifications</span>
              {unreadCount > 0 && <Badge variant="secondary" className="text-[11px]">{unreadCount} unread</Badge>}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              {recent.length === 0 && (
                <p className="px-2 py-6 text-center text-[13px] text-[#8A8A8A]">No notifications yet.</p>
              )}
              {recent.map((n) => (
                <DropdownMenuItem key={n.id} onClick={() => onOpenNotifications?.()} className="items-start gap-2.5 rounded-lg py-2.5">
                  <span className={cn('mt-1 h-2 w-2 shrink-0 rounded-full', n.is_read ? 'bg-[#D6D6D6]' : 'bg-black dark:bg-white')} />
                  <span className="min-w-0">
                    <span className={cn('block truncate text-[13px]', !n.is_read ? 'font-semibold' : 'font-normal')}>{n.title}</span>
                    <span className="block truncate text-[12px] text-[#6B6B6B]">{n.message}</span>
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setView('inbox')} className="justify-center rounded-lg text-[13px] font-semibold">
              <Inbox className="h-4 w-4" /> Open inbox
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <ThemeToggle theme={theme} onToggle={onToggleTheme} />

        <Separator orientation="vertical" className="mx-2 h-6 bg-[#E2E2E2] dark:bg-[#333333]" />

        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="ghost" className="h-11 gap-2.5 rounded-lg px-2" aria-label="Account menu">
                <Avatar className="h-8 w-8 rounded-lg">
                  <AvatarFallback className="rounded-lg bg-black text-[13px] font-bold text-white dark:bg-white dark:text-black">
                    {(user?.name || 'U').charAt(0).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <span className="hidden max-w-[140px] truncate text-left text-[14px] font-semibold lg:block">
                  {user?.name}
                </span>
              </Button>
            }
          />
          <DropdownMenuContent align="end" sideOffset={8} className="w-60 rounded-xl border-[#E2E2E2] p-1.5 shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
            <DropdownMenuLabel className="min-w-0 px-2.5 py-2">
              <span className="block truncate text-[14px] font-semibold">{user?.name}</span>
              <span className="block truncate text-[12px] font-normal text-[#6B6B6B]">{user?.email}</span>
              <Badge variant="secondary" className="mt-2 text-[10px] font-semibold uppercase tracking-[0.06em]">{user?.role}</Badge>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={() => setView('profile')} className="rounded-lg">
                <UserIcon className="h-4 w-4" /> Profile
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setView('inbox')} className="rounded-lg">
                <Inbox className="h-4 w-4" /> Inbox
                {unreadCount > 0 && <Badge variant="secondary" className="ml-auto text-[10px]">{unreadCount}</Badge>}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setView('driver-apply')} className="rounded-lg">
                <CheckCircle2 className="h-4 w-4" /> Become a driver
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onLogout} className="rounded-lg text-[#D93025]">
              <LogOut className="h-4 w-4" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
