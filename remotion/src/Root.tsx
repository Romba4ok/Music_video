import { Composition } from "remotion";
import { DURATION, Sansara } from "./Sansara";
import { T9, T9_DURATION } from "./T9";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="Sansara" component={Sansara} durationInFrames={DURATION} fps={30} width={1080} height={1920} />
      <Composition id="T9" component={T9} durationInFrames={T9_DURATION} fps={30} width={1080} height={1920} />
    </>
  );
};
