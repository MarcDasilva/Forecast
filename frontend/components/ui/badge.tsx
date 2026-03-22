import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]",
  {
    variants: {
      variant: {
        default: "border-[rgba(245,158,11,0.25)] bg-[rgba(245,158,11,0.14)] text-amber-100",
        muted: "border-[rgba(255,255,255,0.08)] bg-[rgba(255,255,255,0.04)] text-amber-200/75",
        success: "border-[rgba(74,222,128,0.28)] bg-[rgba(74,222,128,0.14)] text-emerald-200",
        warning: "border-[rgba(251,191,36,0.28)] bg-[rgba(251,191,36,0.14)] text-amber-100",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
