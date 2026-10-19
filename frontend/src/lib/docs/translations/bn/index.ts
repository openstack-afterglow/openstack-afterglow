import gettingStarted from './gettingStarted';
import coreGuides from './coreGuides';
import additionalGuides from './additionalGuides';
import platformGuides from './platformGuides';
import mcpGuide from './mcpGuide';

const translations: Record<string, string> = {
	...gettingStarted,
	...coreGuides,
	...additionalGuides,
	...platformGuides,
	...mcpGuide
};

export default translations;
