export const Button = ({ icon: Icon, children, variant = "primary", ...props }) => (
  <button className={`btn ${variant}`} {...props}>
    {Icon && <Icon size={16} />}
    {children}
  </button>
);