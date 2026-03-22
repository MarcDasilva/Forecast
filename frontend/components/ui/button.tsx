import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(245,158,11,0.55)] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-amber-400 text-neutral-950 shadow-[0_14px_40px_rgba(245,158,11,0.18)] hover:bg-amber-300",
        outline:
          "border border-[rgba(245,158,11,0.28)] bg-[rgba(24,16,7,0.82)] text-amber-100 hover:bg-[rgba(55,34,10,0.92)]",
        ghost: "text-amber-100 hover:bg-[rgba(245,158,11,0.1)]",
        secondary:
          "bg-[rgba(245,158,11,0.12)] text-amber-100 hover:bg-[rgba(245,158,11,0.18)]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-11 rounded-md px-5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
