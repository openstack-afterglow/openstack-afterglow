import { createContext, useContext, type ReactNode } from "react";

/** Afterglow-only host controls; upstream chart geometry remains unchanged. */
export interface ChartHostConfig {
  yDomain?: [number, number];
  formatTime?: (timestamp: number) => string;
  reducedMotion: boolean;
}
const HostConfig = createContext<ChartHostConfig>({ reducedMotion: false });
export function ChartHostProvider({ value, children }: { value: ChartHostConfig; children: ReactNode }) {
  return <HostConfig.Provider value={value}>{children}</HostConfig.Provider>;
}
export function useChartHostConfig() {
  return useContext(HostConfig);
}
