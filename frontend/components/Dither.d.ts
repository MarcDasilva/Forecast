declare module "@/components/Dither" {
  import type { FC } from "react";

  type DitherProps = {
    waveSpeed?: number;
    waveFrequency?: number;
    waveAmplitude?: number;
    waveColor?: [number, number, number];
    colorNum?: number;
    pixelSize?: number;
    disableAnimation?: boolean;
    enableMouseInteraction?: boolean;
    mouseRadius?: number;
  };

  const Dither: FC<DitherProps>;

  export default Dither;
}
