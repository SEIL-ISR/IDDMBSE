clear all

close all

% Base-configuration, multiple runs

bag_dir = 'SensorBags';
filePattern = fullfile(bag_dir, '*.bag');
theFiles = dir(filePattern);


% Read all Pose Topics

for k = 1 : length(theFiles)
    run_bag = rosbag(theFiles(k).name);
    runs_poseTopics = select(run_bag, 'Topic','/odometry/filtered');
    runs_pose_bags(k) = runs_poseTopics;    
end


% Plot the trajectories from auto runs

for k = 1 : length(theFiles)
    runs_pose_msgs= readMessages(runs_pose_bags(k),'DataFormat','struct');
    xPoints = cellfun(@(m) double(m.Pose.Pose.Position.X),runs_pose_msgs);
    yPoints = cellfun(@(m) double(m.Pose.Pose.Position.Y),runs_pose_msgs);
    zPoints = cellfun(@(m) double(m.Pose.Pose.Position.Z),runs_pose_msgs);
    plot3(xPoints,yPoints,zPoints,'LineWidth',0.5)
    hold on
end

grid on

title('3-D Trajectory Plots of Varios Design Configurations')
xlabel('x')
ylabel('y')
zlabel('z')


hold off

% Metrics
pathlen = zeros(length(theFiles),1);
TTCs = zeros(length(theFiles),1);
CEGs = zeros(length(theFiles),1);

for k = 1 : length(theFiles)
    runs_pose_msgs= readMessages(runs_pose_bags(k),'DataFormat','struct');
    xPoints = cellfun(@(m) double(m.Pose.Pose.Position.X),runs_pose_msgs);
    yPoints = cellfun(@(m) double(m.Pose.Pose.Position.Y),runs_pose_msgs);
    zPoints = cellfun(@(m) double(m.Pose.Pose.Position.Z),runs_pose_msgs);
    [arclen, seglen] = arclength(xPoints,yPoints,zPoints);
    pathlen(k) = arclen;
    pos_time_stmps = cellfun(@(m) double(m.Header.Stamp.Sec),runs_pose_msgs);
    TTCs(k) = pos_time_stmps(length(pos_time_stmps))- pos_time_stmps(1);
    CEGs(k) = sum(abs(gradient(zPoints)));
end

metrics= horzcat(TTCs, pathlen);


figure (2)
scatter(pathlen,TTCs,'filled')   % draw the scatter plot
% ax = gca;
% ax.XDir = 'reverse';
%view(-31,14)
xlabel('Path Length (m)')
ylabel('Time To Completion(s)')

% Adjust the weights
weights = [0.5 0.5];
optsign = [-1 -1];
MAVF_vec = MAVF(metrics, weights, optsign);

[optimal_mavf, optimal_bag_id] = max(MAVF_vec)

fprintf("The Optimal Bag Configuration is:")
theFiles(optimal_bag_id).name

%% Function Definitions
%
function MAVF_vec = MAVF(metrics, weights, optsign)
assert(length(weights)==length(optsign));
m1 = metrics(:,1);
m2 = metrics(:,2);
N_bags = length(m1);

SAVFs = zeros(size(metrics))
weighted_SAVFs = zeros(size(metrics))
% Compute SAVFs

% Outer loop for #metrics
for m = 1:length(weights)
    %Inner loop for # of bags/designs to be evaluated
    % maximizing metrics
    if optsign(m)==1
        for l = 1:N_bags
            SAVFs(l,m) = (metrics(l,m) - min(metrics(:,m))) / (max(metrics(:,m)) - min(metrics(:,m)))  
        end
    else
        for l = 1:N_bags
            SAVFs(l,m) = (max(metrics(:,m)) - metrics(l,m)) / (max(metrics(:,m)) - min(metrics(:,m)))  
        end
    end
end

% MAVF
MAVF_vec = zeros(size(N_bags))

for g = 1:length(weights)
    weighted_SAVFs(:,g) = weights(g)*SAVFs(:,g)
end

for h = 1:length(weights)
    MAVF_vec = MAVF_vec + weighted_SAVFs(:,h)
end
 
end


function [arclen,seglen] = arclength(px,py,varargin)



% arclength: compute arc length of a space curve, or any curve represented as a sequence of points
% usage: [arclen,seglen] = arclength(px,py)         % a 2-d curve
% usage: [arclen,seglen] = arclength(px,py,pz)      % a 3-d space curve
% usage: [arclen,seglen] = arclength(px,py,method)  % specifies the method used
%
% Computes the arc length of a function or any
% general 2-d, 3-d or higher dimensional space
% curve using various methods.
%
% arguments: (input)
%  px, py, pz, ... - vectors of length n, defining points
%        along the curve. n must be at least 2. Replicate
%        points should not be present in the curve.
%
%  method - (OPTIONAL) string flag - denotes the method
%        used to compute the arc length of the curve.
%
%        method may be any of 'linear', 'spline', or 'pchip',
%        or any simple contraction thereof, such as 'lin',
%        'sp', or even 'p'.
%        
%        method == 'linear' --> Uses a linear chordal
%               approximation to compute the arc length.
%               This method is the most efficient.
%
%        method == 'pchip' --> Fits a parametric pchip
%               approximation, then integrates the
%               segments numerically.
%
%        method == 'spline' --> Uses a parametric spline
%               approximation to fit the curves, then
%               integrates the segments numerically.
%               Generally for a smooth curve, this
%               method may be most accurate.
%
%        DEFAULT: 'linear'
%
%
% arguments: (output)
%  arclen - scalar total arclength of all curve segments
%
%  seglen - arclength of each independent curve segment
%           there will be n-1 segments for which the
%           arc length will be computed.
%
%
% Example:
% % Compute the length of the perimeter of a unit circle
% theta = linspace(0,2*pi,10);
% x = cos(theta);
% y = sin(theta);
%
% % The exact value is
% 2*pi
% % ans =
% %          6.28318530717959
%
% % linear chord lengths
% arclen = arclength(x,y,'l')
% % arclen =
% %           6.1564
%
% % Integrated pchip curve fit
% arclen = arclength(x,y,'p')
% % arclen =
% %          6.2782
%
% % Integrated spline fit
% arclen = arclength(x,y,'s')
% % arclen =
% %           6.2856
%
% Example:
% % A (linear) space curve in 5 dimensions
% x = 0:.25:1;
% y = x;
% z = x;
% u = x;
% v = x;
%
% % The length of this curve is simply sqrt(5)
% % since the "curve" is merely the diagonal of a
% % unit 5 dimensional hyper-cube.
% [arclen,seglen] = arclength(x,y,z,u,v,'l')
% % arclen =
% %           2.23606797749979
% % seglen =
% %         0.559016994374947
% %         0.559016994374947
% %         0.559016994374947
% %         0.559016994374947
%
%
% See also: interparc, spline, pchip, interp1
%
% Author: John D'Errico
% e-mail: woodchips@rochester.rr.com
% Release: 1.0
% Release date: 3/10/2010
% unpack the arguments and check for errors
if nargin < 2
  error('ARCLENGTH:insufficientarguments', ...
    'at least px and py must be supplied')
end
n = length(px);
% are px and py both vectors of the same length?
if ~isvector(px) || ~isvector(py) || (length(py) ~= n)
  error('ARCLENGTH:improperpxorpy', ...
    'px and py must be vectors of the same length')
elseif n < 2
  error('ARCLENGTH:improperpxorpy', ...
    'px and py must be vectors of length at least 2')
end
% compile the curve into one array
data = [px(:),py(:)];
% defaults for method and tol
method = 'linear';
% which other arguments are included in varargin?
if numel(varargin) > 0
  % at least one other argument was supplied
  for i = 1:numel(varargin)
    arg = varargin{i};
    if ischar(arg)
      % it must be the method
      validmethods = {'linear' 'pchip' 'spline'};
      ind = strmatch(lower(arg),validmethods);
      if isempty(ind) || (length(ind) > 1)
        error('ARCLENGTH:invalidmethod', ...
          'Invalid method indicated. Only ''linear'',''pchip'',''spline'' allowed.')
      end
      method = validmethods{ind};
      
    else
      % it must be pz, defining a space curve in higher dimensions
      if numel(arg) ~= n
        error('ARCLENGTH:inconsistentpz', ...
          'pz was supplied, but is inconsistent in size with px and py')
      end
      
      % expand the data array to be a 3-d space curve
      data = [data,arg(:)]; %#ok
    end
  end
  
end
% what dimension do we live in?
nd = size(data,2);
% compute the chordal linear arclengths
seglen = sqrt(sum(diff(data,[],1).^2,2));
arclen = sum(seglen);
% we can quit if the method was 'linear'.
if strcmpi(method,'linear')
  % we are now done. just exit
  return
end
% 'spline' or 'pchip' must have been indicated,
% so we will be doing an integration. Save the
% linear chord lengths for later use.
chordlen = seglen;
% compute the splines
spl = cell(1,nd);
spld = spl;
diffarray = [3 0 0;0 2 0;0 0 1;0 0 0];
for i = 1:nd
  switch method
    case 'pchip'
      spl{i} = pchip([0;cumsum(chordlen)],data(:,i));
    case 'spline'
      spl{i} = spline([0;cumsum(chordlen)],data(:,i));
      nc = numel(spl{i}.coefs);
      if nc < 4
        % just pretend it has cubic segments
        spl{i}.coefs = [zeros(1,4-nc),spl{i}.coefs];
        spl{i}.order = 4;
      end
  end
  
  % and now differentiate them
  xp = spl{i};
  xp.coefs = xp.coefs*diffarray;
  xp.order = 3;
  spld{i} = xp;
end
% numerical integration along the curve
polyarray = zeros(nd,3);
for i = 1:spl{1}.pieces
  % extract polynomials for the derivatives
  for j = 1:nd
    polyarray(j,:) = spld{j}.coefs(i,:);
  end
  
  % integrate the arclength for the i'th segment
  % using quadgk for the integral. I could have
  % done this part with an ode solver too.
  seglen(i) = quadgk(@(t) segkernel(t),0,chordlen(i));
end
% and sum the segments
arclen = sum(seglen);
% ==========================
%   end main function
% ==========================
%   begin nested functions
% ==========================
  function val = segkernel(t)
    % sqrt((dx/dt)^2 + (dy/dt)^2)
    
    val = zeros(size(t));
    for k = 1:nd
      val = val + polyval(polyarray(k,:),t).^2;
    end
    val = sqrt(val);
    
  end % function segkernel
end % function arclength



function [A varargout]=prtp(B)
A=[]; varargout{1}=[];
sz1=size(B,1);
jj=0; kk(sz1)=0;
c(sz1,size(B,2))=0;
bb=c;
for k=1:sz1
  j=0;
  ak=B(k,:);
  for i=1:sz1
    if i~=k
      j=j+1;
      bb(j,:)=ak-B(i,:);
    end
  end
  if any(bb(1:j,:)'<0)
    jj=jj+1;
    c(jj,:)=ak;
    kk(jj)=k;
  end
end
if jj
  A=c(1:jj,:);
  varargout{1}=kk(1:jj);
else
  warning('Points:Pareto',...
    'There are no Pareto points. The result is an empty matrix.')
end

end
