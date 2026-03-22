import * as React from "react";

import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-md border border-[rgba(245,158,11,0.2)] bg-[rgba(13,10,7,0.92)] px-3 py-2 text-sm text-amber-50 outline-none ring-offset-background transition-colors placeholder:text-amber-100/35 focus-visible:ring-2 focus-visible:ring-[rgba(245,158,11,0.42)] disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
