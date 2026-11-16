/**
 * The link component rjui wraps a Button's `href` in on this host.
 *
 * rjui emits `<Link href>` from the adapter named by `web_framework` in
 * rjui.config.json, and its default is Next.js (`next/link`). This host is
 * Vite + React with no router, so its config declares its own adapter, and
 * this is the link it imports: an anchor, which is what next/link draws.
 */
import React from 'react';

type LinkProps = React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string };

export default function Link({ href, children, ...rest }: LinkProps) {
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  );
}
