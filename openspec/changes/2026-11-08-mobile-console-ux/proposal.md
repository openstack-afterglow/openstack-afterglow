# Proposal: mobile-console-ux

Mobile (<768px, DESIGN.md) console feedback from the owner. Tablet/desktop behavior must not change.

1. Card-mode tables: replace per-column sort/filter icons with ONE filter button; its panel applies all filters in a batch with a "조회하기" (apply) button that re-queries the list.
2. Auto refresh: on mobile show only a single round icon refresh button; remove the interval select.
3. Instance card (mobile): show name, flavor, IP (plus status pill and the actions menu); drop image, id row and the details disclosure.
4. Instance detail (mobile): name on top, small status pill beside it, below only Stop and Reboot; when stopped only Start. Remove auto refresh select; rename/console/resize/etc. move into the overflow menu.
5. Navigation drawer (mobile): opens full screen; top search field covers resources AND services (remove the "리소스 검색" button and the separate service search); sections are Hub and Services; topology, activity and usage report are hidden by default on mobile.
6. Header (mobile & desktop): profile menu holds logout, account, my resources, notifications, light/dark toggle. Standalone docs, theme, bell, and logout buttons leave the header bar. Desktop header bar retains the Cloud Shell trigger, user/admin mode toggle, and language selector.

Out of scope: backend, tutorials.
