"use client";

import { motion } from "motion/react";
import { memo, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "$lib/vendor/bklit-ui/lib/utils";
import { useChart, useChartStable } from "./chart-context";
import { useChartHostConfig } from "./host-config";

export interface BarXAxisProps {
  /** Width of the date ticker box for fade calculation. Default: 50 */
  tickerHalfWidth?: number;
  /** Whether to show all labels or skip some for dense data. Default: false */
  showAllLabels?: boolean;
  /** Maximum number of labels to show. Default: 12 */
  maxLabels?: number;
  /** Compact visible labels; category identity and hover data remain unchanged. */
  formatLabel?: (label: string) => string;
}

interface BarXAxisLabelProps {
  label: string;
  formattedLabel?: string;
  x: number;
  crosshairX: number | null;
  isHovering: boolean;
  tickerHalfWidth: number;
  align: "start" | "center" | "end";
  maxWidth: number;
}

function BarXAxisLabel({
  label,
  formattedLabel,
  x,
  crosshairX,
  isHovering,
  tickerHalfWidth,
  align,
  maxWidth,
}: BarXAxisLabelProps) {
  const { reducedMotion } = useChartHostConfig();
  const fadeBuffer = 20;
  const fadeRadius = tickerHalfWidth + fadeBuffer;

  let opacity = 1;
  if (isHovering && crosshairX !== null) {
    const distance = Math.abs(x - crosshairX);
    if (distance < tickerHalfWidth) {
      opacity = 0;
    } else if (distance < fadeRadius) {
      opacity = (distance - tickerHalfWidth) / fadeBuffer;
    }
  }

  // Keep endpoint labels inside the plot; complete categories remain in the tooltip/table.
  return (
    <div
      className="absolute"
      style={{
        left: x,
        bottom: 12,
        width: 0,
        display: "flex",
        justifyContent: align === "start" ? "flex-start" : align === "end" ? "flex-end" : "center",
      }}
    >
      <motion.span
        animate={{ opacity }}
        className={cn("whitespace-nowrap text-chart-label text-xs")}
        style={{ maxWidth, flexShrink: 0, overflow: "hidden", textOverflow: "ellipsis" }}
        title={label}
        initial={{ opacity: 1 }}
        transition={{ duration: reducedMotion ? 0 : 0.4, ease: "easeInOut" }}
      >
        {formattedLabel ?? label}
      </motion.span>
    </div>
  );
}

export function BarXAxis(props: BarXAxisProps) {
  const { containerRef, barScale } = useChartStable();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const container = containerRef.current;
  if (!(mounted && container)) {
    return null;
  }

  if (!barScale) {
    return null;
  }

  return <BarXAxisInner {...props} container={container} />;
}

const BarXAxisInner = memo(function BarXAxisInner({
  tickerHalfWidth = 50,
  showAllLabels = false,
  maxLabels: requestedLabels = 12,
  formatLabel,
  container,
}: BarXAxisProps & { container: HTMLDivElement }) {
  const { margin, tooltipData, barScale, bandWidth, barXAccessor, data, innerWidth } =
    useChart();
  const maxLabels = Math.max(2, Math.min(requestedLabels, Math.floor(innerWidth / 120) + 1));

  // Generate labels for each bar
  const labelsToShow = useMemo(() => {
    if (!(barScale && bandWidth && barXAccessor)) {
      return [];
    }

    const allLabels = data.map((d) => {
      const label = barXAccessor(d);
      const bandX = barScale(label) ?? 0;
      // Center the label under the bar group
      const x = bandX + bandWidth / 2 + margin.left;
      return { label, x };
    });

    // If showAllLabels is true or we have fewer than maxLabels, show all
    if (showAllLabels || allLabels.length <= maxLabels) {
      return allLabels;
    }

    // Keep both endpoints and distribute the remaining ticks uniformly.
    return Array.from({ length: maxLabels }, (_, i) =>
      allLabels[Math.round(i * (allLabels.length - 1) / (maxLabels - 1))]!
    );
  }, [
    barScale,
    bandWidth,
    barXAccessor,
    data,
    margin.left,
    showAllLabels,
    maxLabels,
  ]);

  const isHovering = tooltipData !== null;
  const crosshairX = tooltipData ? tooltipData.x + margin.left : null;

  return createPortal(
    <div className="pointer-events-none absolute inset-0">
      {labelsToShow.map((item, index) => {
        const first = index === 0;
        const last = index === labelsToShow.length - 1;
        const previous = labelsToShow[index - 1];
        const next = labelsToShow[index + 1];
        // Endpoint labels occupy half a neighbour interval; centered labels occupy both halves.
        const maxWidth = first && last ? margin.left + innerWidth - item.x
          : first ? (next!.x - item.x) / 2 - 4
          : last ? (item.x - previous!.x) / 2 - 4
          : Math.min(item.x - previous!.x, next!.x - item.x) - 8;
        return <BarXAxisLabel
          align={first ? "start" : last ? "end" : "center"}
          maxWidth={Math.max(0, maxWidth)}
          crosshairX={crosshairX}
          isHovering={isHovering}
          key={`${item.label}-${item.x}`}
          label={item.label}
          formattedLabel={formatLabel?.(item.label)}
          tickerHalfWidth={tickerHalfWidth}
          x={item.x}
        />;
      })}
    </div>,
    container
  );
});

BarXAxis.displayName = "BarXAxis";

export default BarXAxis;
