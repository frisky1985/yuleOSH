import React from "react";

const Link = ({
  href,
  children,
  ...props
}: {
  href: string;
  children: React.ReactNode;
  [key: string]: any;
}) => {
  return React.createElement("a", { href, ...props }, children);
};

export default Link;
