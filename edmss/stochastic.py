# Copyright (c) 2022, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# This work is licensed under a Creative Commons
# Attribution-NonCommercial-ShareAlike 4.0 International License.
# You should have received a copy of the license along with this
# work. If not, see http://creativecommons.org/licenses/by-nc-sa/4.0/

import numpy as np
import torch
import math

def image_batching(input, 
        img_shape_y, 
        img_shape_x, 
        patch_shape_y, 
        patch_shape_x,
        batch_size,
        overlap_pix,
        boundary_pix,
        input_interp=None
        ):
    '''
    full image --> batch of patched image
    batch_size: original batch size without patching
    overlap_pix: overlapping size between patches
    boundary_pix: boundary pixel size that will be cropped
    '''
    patch_num_x = math.ceil(img_shape_x/(patch_shape_x-overlap_pix-boundary_pix))
    patch_num_y = math.ceil(img_shape_y/(patch_shape_y-overlap_pix-boundary_pix))
    padded_shape_x = (patch_shape_x-overlap_pix-boundary_pix) * (patch_num_x-1) + patch_shape_x + boundary_pix
    padded_shape_y = (patch_shape_y-overlap_pix-boundary_pix) * (patch_num_y-1) + patch_shape_y + boundary_pix
    pad_x_right = padded_shape_x - img_shape_x - boundary_pix
    pad_y_right = padded_shape_y - img_shape_y - boundary_pix
    input_padded = torch.zeros(input.shape[0], input.shape[1], padded_shape_y, padded_shape_x).to(input.device)
    image_padding = torch.nn.ReflectionPad2d((boundary_pix, pad_x_right, boundary_pix, pad_y_right)).to(input.device) #(padding_left,padding_right,padding_top,padding_bottom)
    input_padded = image_padding(input)
    patch_num = patch_num_x*patch_num_y
    if input_interp is not None:
        output = torch.zeros(patch_num*batch_size, input.shape[1]+input_interp.shape[1], patch_shape_y, patch_shape_x).to(input.device)
    else:
        output = torch.zeros(patch_num*batch_size, input.shape[1], patch_shape_y, patch_shape_x).to(input.device)
    for x_index in range(patch_num_x):
        for y_index in range(patch_num_y): 
            x_start = x_index*(patch_shape_x-overlap_pix-boundary_pix) 
            y_start = y_index*(patch_shape_y-overlap_pix-boundary_pix)           
            if input_interp is not None:
                output[(x_index*patch_num_y+y_index)*batch_size:(x_index*patch_num_y+y_index+1)*batch_size,] = torch.cat((input_padded[:,:,y_start:y_start+patch_shape_y, x_start:x_start+patch_shape_x], input_interp), dim=1)
            else:
                output[(x_index*patch_num_y+y_index)*batch_size:(x_index*patch_num_y+y_index+1)*batch_size,] = input_padded[:,:,y_start:y_start+patch_shape_y, x_start:x_start+patch_shape_x] 
    return output

def image_fuse(input,
        img_shape_y, 
        img_shape_x, 
        patch_shape_y, 
        patch_shape_x,
        batch_size,
        overlap_pix,
        boundary_pix
        ):
    '''
    batch of patched image --> full image
    batch_size: original batch size without patching
    overlap_pix: overlapping size between patches
    boundary_pix: boundary pixel size that will be cropped
    '''
    patch_num_x = math.ceil(img_shape_x/(patch_shape_x-overlap_pix-boundary_pix))
    patch_num_y = math.ceil(img_shape_y/(patch_shape_y-overlap_pix-boundary_pix))
    padded_shape_x = (patch_shape_x-overlap_pix-boundary_pix) * (patch_num_x-1) + patch_shape_x + boundary_pix
    padded_shape_y = (patch_shape_y-overlap_pix-boundary_pix) * (patch_num_y-1) + patch_shape_y + boundary_pix
    pad_x_right = padded_shape_x - img_shape_x - boundary_pix
    pad_y_right = padded_shape_y - img_shape_y - boundary_pix
    residual_x = patch_shape_x - pad_x_right # residual pixels in the last patch
    residual_y = patch_shape_y - pad_y_right # residual pixels in the last patch
    output = torch.zeros(batch_size, input.shape[1], img_shape_y, img_shape_x, device=input.device)
    one_map = torch.ones(1, 1, input.shape[2], input.shape[3], device=input.device)
    count_map = torch.zeros(1, 1, img_shape_y, img_shape_x, device=input.device) # to count the overlapping times

    for x_index in range(patch_num_x):
        for y_index in range(patch_num_y): 
            x_start = x_index*(patch_shape_x-overlap_pix-boundary_pix) 
            y_start = y_index*(patch_shape_y-overlap_pix-boundary_pix)  
            if (x_index==patch_num_x-1) and (y_index!=patch_num_y-1):
                output[:,:,y_start:y_start+patch_shape_y-2*boundary_pix, x_start:] += input[(x_index*patch_num_y+y_index)*batch_size:(x_index*patch_num_y+y_index+1)*batch_size,:,boundary_pix:patch_shape_y-boundary_pix, boundary_pix:residual_x+boundary_pix]
                count_map[:,:,y_start:y_start+patch_shape_y-2*boundary_pix, x_start:] += one_map[:,:,boundary_pix:patch_shape_y-boundary_pix, boundary_pix:residual_x+boundary_pix]               
            elif (y_index==patch_num_y-1) and ((x_index!=patch_num_x-1)):
                output[:,:,y_start:, x_start:x_start+patch_shape_x-2*boundary_pix] += input[(x_index*patch_num_y+y_index)*batch_size:(x_index*patch_num_y+y_index+1)*batch_size,:,boundary_pix:residual_y+boundary_pix, boundary_pix:patch_shape_x-boundary_pix]
                count_map[:,:,y_start:, x_start:x_start+patch_shape_x-2*boundary_pix] += one_map[:,:,boundary_pix:residual_y+boundary_pix, boundary_pix:patch_shape_x-boundary_pix]          
            elif (x_index==patch_num_x-1 and y_index==patch_num_y-1):
                output[:,:,y_start:, x_start:] += input[(x_index*patch_num_y+y_index)*batch_size:(x_index*patch_num_y+y_index+1)*batch_size,:,boundary_pix:residual_y+boundary_pix, boundary_pix:residual_x+boundary_pix]
                count_map[:,:,y_start:, x_start:] += one_map[:,:,boundary_pix:residual_y+boundary_pix, boundary_pix:residual_x+boundary_pix]            
            else:
                output[:,:,y_start:y_start+patch_shape_y-2*boundary_pix, x_start:x_start+patch_shape_x-2*boundary_pix] += input[(x_index*patch_num_y+y_index)*batch_size:(x_index*patch_num_y+y_index+1)*batch_size,:,boundary_pix:patch_shape_y-boundary_pix, boundary_pix:patch_shape_x-boundary_pix]
                count_map[:,:,y_start:y_start+patch_shape_y-2*boundary_pix, x_start:x_start+patch_shape_x-2*boundary_pix] += one_map[:,:,boundary_pix:patch_shape_y-boundary_pix, boundary_pix:patch_shape_x-boundary_pix]
    return output/count_map


def edm_sampler(
    net,
    latents,
    img_lr,
    class_labels=None,
    randn_like=torch.randn_like,
    img_shape=448,
    patch_shape=448, 
    overlap_pix=4, 
    boundary_pix=2, 
    mean_hr=None,
    lead_time_label=None,
    num_steps=18,
    sigma_min=0.002,
    sigma_max=800,
    rho=7,
    S_churn=0,
    S_min=0,
    S_max=float("inf"),
    S_noise=1,
):  
    # Adjust noise levels based on what's supported by the network.
    "Proposed EDM sampler (Algorithm 2) with minor changes to enable super-resolution."
    sigma_min = max(sigma_min, net.sigma_min)
    #sigma_max = min(sigma_max, net.sigma_max)
    print(sigma_max, sigma_min)
    if isinstance(img_shape, tuple):
        img_shape_x, img_shape_y = img_shape
    else:
        img_shape_x = img_shape_y = img_shape

    # Time step discretization.
    step_indices = torch.arange(num_steps, dtype=torch.float64, device=latents.device)
    t_steps = (
        sigma_max ** (1 / rho)
        + step_indices
        / (num_steps - 1)
        * (sigma_min ** (1 / rho) - sigma_max ** (1 / rho))
    ) ** rho
    t_steps = torch.cat(
        [net.round_sigma(t_steps), torch.zeros_like(t_steps[:1])]
    )  # t_N = 0

    b = latents.shape[0]
    Nx = torch.arange(img_shape_x)
    Ny = torch.arange(img_shape_y)
    grid = torch.stack(torch.meshgrid(Ny, Nx, indexing="ij"), dim=0)[None,].expand(b, -1, -1, -1)

    # conditioning = [mean_hr, img_lr, global_lr, pos_embd]
    batch_size = img_lr.shape[0]
    x_lr = img_lr
    if mean_hr is not None:
        x_lr = torch.cat((mean_hr.expand(x_lr.shape[0], -1, -1, -1), x_lr), dim=1)
    global_index = None        
      
    # input and position padding + patching
    if (patch_shape!=img_shape_x or patch_shape!=img_shape_y):
        input_interp = torch.nn.functional.interpolate(img_lr, (patch_shape, patch_shape), mode='bilinear') 
        x_lr = image_batching(x_lr, img_shape_y, img_shape_x, patch_shape, patch_shape, batch_size, overlap_pix, boundary_pix, input_interp)
        global_index = image_batching(grid.float(), img_shape_y, img_shape_x, patch_shape, patch_shape, batch_size, overlap_pix, boundary_pix).int()   
    # Main sampling loop.
    x_next = latents.to(torch.float64) * t_steps[0]
    #x_next[:,:5] *= 0.25
    print("per_channel sampler used")
    for i, (t_cur, t_next) in enumerate(zip(t_steps[:-1], t_steps[1:])):  # 0, ..., N-1
        x_cur = x_next
        # Increase noise temporarily.
        gamma = (
            S_churn / num_steps if S_min <= t_cur <= S_max else 0
        )
        t_hat = net.round_sigma(t_cur + gamma * t_cur)

        x_hat = x_cur + (t_hat**2 - t_cur**2).sqrt() * S_noise * randn_like(x_cur)   

        # Euler step. Perform patching operation on score tensor if patch-based generation is used
        # denoised = net(x_hat, t_hat, class_labels,lead_time_label=lead_time_label).to(torch.float64)    #x_lr
        
        if (patch_shape!=img_shape_x or patch_shape!=img_shape_y):
            x_hat_batch = image_batching(x_hat, img_shape_y, img_shape_x, patch_shape, patch_shape, batch_size, overlap_pix, boundary_pix)
        else:
            x_hat_batch = x_hat
        
        x_hat_batch = x_hat_batch.to(latents.device)
        x_lr = x_lr.to(latents.device)
        global_index = global_index.to(latents.device)
        # print(x_hat_batch.device, x_hat.device, x_lr.device, t_hat.device, class_labels, global_index.device, lead_time_label)
        
        denoised = net(x_hat_batch, x_lr, torch.ones([x_hat.shape[0],16,1,1])*t_hat, class_labels, lead_time_label=lead_time_label, global_index=global_index).to(torch.float64)
        if (patch_shape!=img_shape_x or patch_shape!=img_shape_y):
            # print(denoised.device, img_shape_y, img_shape_x, patch_shape, patch_shape, batch_size, overlap_pix, boundary_pix)
            denoised = image_fuse(denoised, img_shape_y, img_shape_x, patch_shape, patch_shape, batch_size, overlap_pix, boundary_pix)       
        d_cur = (x_hat - denoised) / t_hat
        x_next = x_hat + (t_next - t_hat) * d_cur

        # Apply 2nd order correction.
        if i < num_steps - 1:
            if (patch_shape!=img_shape_x or patch_shape!=img_shape_y):
                x_next_batch = image_batching(x_next, img_shape_y, img_shape_x, patch_shape, patch_shape, batch_size, overlap_pix, boundary_pix)
            else:
                x_next_batch = x_next
            # ask about this fix
            x_next_batch = x_next_batch.to(latents.device)
            denoised = net(x_next_batch, x_lr, torch.ones([x_hat.shape[0],16,1,1])*t_next, class_labels, lead_time_label=lead_time_label,global_index=global_index).to(torch.float64)
            if (patch_shape!=img_shape_x or patch_shape!=img_shape_y):
                denoised = image_fuse(denoised, img_shape_y, img_shape_x, patch_shape, patch_shape, batch_size, overlap_pix, boundary_pix)
            d_prime = (x_next - denoised) / t_next
            x_next = x_hat + (t_next - t_hat) * (0.5 * d_cur + 0.5 * d_prime)
    return x_next
    
