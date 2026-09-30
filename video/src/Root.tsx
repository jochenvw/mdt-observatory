import React from 'react';
import {Composition} from 'remotion';
import {Movie} from './Movie';
import story from './story.json';

export const Root: React.FC = () => <Composition
  id="MDTObservatory"
  component={Movie}
  durationInFrames={story.duration * story.fps}
  width={story.width}
  height={story.height}
  fps={story.fps}
  defaultProps={{captions: true, music: true}}
/>;
