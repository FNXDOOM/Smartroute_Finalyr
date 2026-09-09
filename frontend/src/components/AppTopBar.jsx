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
    <header className="app-topbar sticky top-0 z-40 flex h-14 shrink-0 items-center gap-2 border-b bg-background/90 px-3 backdrop-blur supports-backdrop-filter:bg-background/80 md:px-5">
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
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <span className="hidden truncate sm:inline">{meta.crumb.split(' / ')[0]}</span>
          <ChevronRight className="hidden h-3 w-3 sm:inline" />
          <span className="truncate font-medium text-foreground/80">{meta.crumb.split(' / ')[1] || meta.crumb}</span>
        </nav>
        <h1 className="truncate text-[15px] font-bold leading-tight tracking-tight">{meta.title}</h1>
      </div>

      <div className="flex items-center gap-1.5">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="ghost" size="icon" className="relative" aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ''}`}>
                <Bell className="h-4 w-4" />
                {unreadCount > 0 && (
                  <Badge variant="destructive" className="absolute -right-1 -top-1 h-4 min-w-4 justify-center px-1 text-[10px] leading-none">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </Badge>
                )}
              </Button>
            }
          />
          <DropdownMenuContent align="end" sideOffset={8} className="w-80">
            <DropdownMenuLabel className="flex items-center justify-between">
              <span>Notifications</span>
              {unreadCount > 0 && <Badge variant="secondary" className="text-[10px]">{unreadCount} unread</Badge>}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              {recent.length === 0 && (
                <p className="px-2 py-4 text-center text-xs text-muted-foreground">No notifications yet.</p>
              )}
              {recent.map((n) => (
                <DropdownMenuItem key={n.id} onClick={() => onOpenNotifications?.()} className="items-start gap-2.5 py-2">
                  <span className={cn('mt-0.5 h-2 w-2 shrink-0 rounded-full', n.is_read ? 'bg-muted' : 'bg-primary')} />
                  <span className="min-w-0">
                    <span className={cn('block truncate text-xs', !n.is_read ? 'font-bold' : 'font-medium')}>{n.title}</span>
                    <span className="block truncate text-[11px] text-muted-foreground">{n.message}</span>
                  </span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setView('inbox')} className="justify-center text-xs font-semibold">
              <Inbox className="h-3.5 w-3.5" /> Open inbox
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <ThemeToggle theme={theme} onToggle={onToggleTheme} />

        <Separator orientation="vertical" className="mx-1 h-6" />

        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="ghost" className="h-9 gap-2 px-1.5" aria-label="Account menu">
                <Avatar className="h-7 w-7">
                  <AvatarFallback className="bg-primary/10 text-xs font-bold text-primary">
                    {(user?.name || 'U').charAt(0).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <span className="hidden max-w-[140px] truncate text-left text-xs font-semibold lg:block">
                  {user?.name}
                </span>
              </Button>
            }
          />
          <DropdownMenuContent align="end" sideOffset={8} className="w-60">
            <DropdownMenuLabel className="min-w-0">
              <span className="block truncate text-sm font-bold">{user?.name}</span>
              <span className="block truncate text-[11px] font-normal text-muted-foreground">{user?.email}</span>
              <Badge variant="secondary" className="mt-1.5 text-[10px] uppercase">{user?.role}</Badge>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={() => setView('profile')}>
                <UserIcon className="h-4 w-4" /> Profile
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setView('inbox')}>
                <Inbox className="h-4 w-4" /> Inbox
                {unreadCount > 0 && <Badge variant="secondary" className="ml-auto text-[10px]">{unreadCount}</Badge>}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setView('driver-apply')}>
                <CheckCircle2 className="h-4 w-4" /> Become a driver
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onLogout} className="text-destructive">
              <LogOut className="h-4 w-4" /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
