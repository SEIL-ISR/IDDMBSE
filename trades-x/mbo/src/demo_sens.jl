l_s= 15;
l_ch = 16;
l_scans = 1875
l_rmax = 100
l_pow = 80
l_vfov = 0.526


c_hres = 720
c_vres = 540
c_rmax = 50
c_rmin = 0.5
c_pow = 3
c_s = 30
c_hfov = 1.047

d_hres = 1920
d_vres = 1080
d_rmax =6
d_hfov = 1.501
d_vfov = 0.9948
c_pow = 10
d_s = 15

la_hfov = 4.71
la_vfov = 1.57
la_rmax = 20
la_pow = 30
la_s = 50
la_rmin = 0.1
la_scans = 720

l_ch*l_scans

l_s*l_scans

l_ch*l_s

16* c_hres * c_vres

16* c_s * c_hres

16* c_s * c_vres


8*d_hres*d_vres
8*d_s*d_hres
8*d_s*d_vres



2*la_s
2*la_scans

# Coverage

th = l_vfov/2
b=0.5
2*π*(l_rmax)^2*(cos(th))^2*sin(th) + 2*π*(l_rmax)*b*(cos(th))^2

using ForwardDiff

function coverage(l_rmax, vfov, b)
    th = vfov/2
    cov = 2 * (π / 3)  * (l_rmax)^3 * (cos(th))^2 * sin(th) +
        (π / 3) * (l_rmax)^2 * b * (cos(th))^2 -
    (π / 3) * b * (cot(th))^2
    return cov
end

println("lidar coverage(100, 0.526, 0.5) = ", coverage(100, 0.526, 0.5))
println("  gradient wrt (max_range, v_fov, b) = ",
        ForwardDiff.gradient(x -> coverage(x[1], x[2], x[3]), [100.0, 0.526, 0.5]))


function cam_coverage(c_rmax, hfov, vfov, b)
    th = vfov/2
    cov = (π / 6) * (c_rmax) * tan(hfov / 2) * ((c_rmax^2) * tan(vfov / 2) + 2 * b * c_rmax) - (b^2) * cot(vfov / 2)
    return cov
    
end

println("rgb camera cam_coverage(60, 1.047, 1.273, 0.5) = ", cam_coverage(60.0, c_hfov, 1.273, 0.5))
println("  gradient wrt (max_range, h_fov, v_fov, b) = ",
        ForwardDiff.gradient(x -> cam_coverage(x[1], x[2], x[3], x[4]), [60.0, 1.047, 1.273, 0.5]))

println("depth camera cam_coverage(6, 1.501, 0.9948, 0.5) = ", cam_coverage(d_rmax, d_hfov, d_vfov, 0.5))
println("  gradient wrt (max_range, h_fov, v_fov, b) = ",
        ForwardDiff.gradient(x -> cam_coverage(x[1], x[2], x[3], x[4]), [6.0, 1.501, 0.9948, 0.5]))

function laser_coverage(la_hfov, la_rmax, b)
    sen_cov = (la_hfov / 2) * (la_rmax)^2 * b
    return sen_cov

end


println("laser laser_coverage(4.71, 20, 0.1) = ", laser_coverage(la_hfov, la_rmax, 0.1))
println("  gradient wrt (h_fov, max_range, b) = ",
        ForwardDiff.gradient(x -> laser_coverage(x[1], x[2], x[3]), [4.71, 20.0, 0.1]))
