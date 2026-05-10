import * as React from "react"
import { cn } from "@/lib/utils"

interface CollapsibleProps extends React.HTMLAttributes<HTMLDivElement> {
  open?: boolean
  onOpenChange?: (open: boolean) => void
  children: React.ReactNode
}

interface CollapsibleTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean
}

interface CollapsibleContentProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

const CollapsibleContext = React.createContext<{
  open: boolean
  onOpenChange: (open: boolean) => void
}>({
  open: false,
  onOpenChange: () => {}
})

const Collapsible = React.forwardRef<HTMLDivElement, CollapsibleProps>(
  ({ className, open: controlledOpen, onOpenChange, children, ...props }, ref) => {
    const [internalOpen, setInternalOpen] = React.useState(false)
    const isControlled = controlledOpen !== undefined
    const open = isControlled ? controlledOpen : internalOpen
    
    const handleOpenChange = React.useCallback((newOpen: boolean) => {
      if (onOpenChange) {
        onOpenChange(newOpen)
      }
      if (!isControlled) {
        setInternalOpen(newOpen)
      }
    }, [onOpenChange, isControlled])

    return (
      <CollapsibleContext.Provider value={{ open, onOpenChange: handleOpenChange }}>
        <div ref={ref} className={cn(className)} {...props}>
          {children}
        </div>
      </CollapsibleContext.Provider>
    )
  }
)
Collapsible.displayName = "Collapsible"

const CollapsibleTrigger = React.forwardRef<HTMLButtonElement, CollapsibleTriggerProps>(
  ({ className, asChild, children, onClick, ...props }, ref) => {
    const { open, onOpenChange } = React.useContext(CollapsibleContext)
    
    const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
      onOpenChange(!open)
      if (onClick) {
        onClick(event)
      }
    }

    if (asChild && React.isValidElement(children)) {
      return React.cloneElement(children, {
        ...children.props,
        onClick: handleClick,
        ref,
      })
    }

    return (
      <button
        ref={ref}
        className={cn(className)}
        onClick={handleClick}
        {...props}
      >
        {children}
      </button>
    )
  }
)
CollapsibleTrigger.displayName = "CollapsibleTrigger"

const CollapsibleContent = React.forwardRef<HTMLDivElement, CollapsibleContentProps>(
  ({ className, children, ...props }, ref) => {
    const { open } = React.useContext(CollapsibleContext)

    if (!open) return null

    return (
      <div ref={ref} className={cn(className)} {...props}>
        {children}
      </div>
    )
  }
)
CollapsibleContent.displayName = "CollapsibleContent"

export { Collapsible, CollapsibleTrigger, CollapsibleContent }