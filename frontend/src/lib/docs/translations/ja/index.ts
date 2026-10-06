import gettingStarted from './gettingStarted';
import coreGuides from './coreGuides';
import additionalGuides from './additionalGuides';
import platformGuides from './platformGuides';

const ja: Readonly<Record<string, string>> = { ...gettingStarted, ...coreGuides, ...additionalGuides, ...platformGuides };

export default ja;
